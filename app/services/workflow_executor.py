import asyncio
from typing import Dict, Any
from app.core.db import AsyncSessionLocal
from app.models.workflow import Workflow, WorkflowRun, WorkflowRunStatus
from app.models.integration import Integration
from app.services.action_registry import get_action_handler

class WorkflowExecutorService:
    MAX_RETRIES = 3

    @staticmethod
    def _interpolate_params(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        class SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"
        safe_context = SafeDict(**context)

        for k, v in params.items():
            if isinstance(v, str):
                try:
                    result[k] = v.format_map(safe_context)
                except Exception:
                    result[k] = v
            elif isinstance(v, dict):
                result[k] = WorkflowExecutorService._interpolate_params(v, context)
            else:
                result[k] = v
        return result

    @staticmethod
    async def execute_workflow(workflow_id: int, run_id: int, initial_context: Dict[str, Any] = None):
        async with AsyncSessionLocal() as session:
            run = await session.get(WorkflowRun, run_id)
            if not run: return

            workflow = await session.get(Workflow, workflow_id)
            if not workflow:
                run.status = WorkflowRunStatus.FAILED
                run.logs += "\nWorkflow not found."
                await session.commit()
                return

            run.status = WorkflowRunStatus.RUNNING
            run.logs += f"Started execution of workflow '{workflow.name}'...\n"
            run.total_tokens = getattr(run, "total_tokens", 0)
            await session.commit()

            step_name = "Unknown"
            context_data: Dict[str, Any] = initial_context.copy() if initial_context else {}

            try:
                for i, step in enumerate(workflow.steps):
                    step_name = step.get("name", f"Step {i+1}")
                    action = step.get("action", "unknown")
                    params = step.get("params", {})
                    fallback_value = params.get("fallback_value")
                    integration_id = params.get("integration_id")

                    for attempt in range(1, WorkflowExecutorService.MAX_RETRIES + 1):
                        try:
                            run.logs += f"Executing step '{step_name}' (Action: {action}) [Attempt {attempt}/{WorkflowExecutorService.MAX_RETRIES}]...\n"
                            await session.commit()

                            if action == "fail":
                                raise Exception("Simulated failure action triggered.")

                            # 1. Fetch Integration Config if needed
                            integration_config = {}
                            if integration_id:
                                integration = await session.get(Integration, integration_id)
                                if not integration:
                                    raise ValueError(f"Integration ID {integration_id} not found.")
                                integration_config = integration.config

                            # 2. Lookup Handler
                            handler = get_action_handler(action)

                            # 3. Execute Handler with Interpolated Params
                            interpolated_params = WorkflowExecutorService._interpolate_params(params, context_data)
                            output_val, tokens_used = await handler(integration_config, interpolated_params, context_data)

                            if tokens_used > 0:
                                run.total_tokens += tokens_used
                                run.logs += f"Step '{step_name}' used {tokens_used} tokens. Output: {output_val}\n"
                            else:
                                run.logs += f"Step '{step_name}' completed successfully. Output: {output_val}\n"
                            
                            context_data[step_name] = output_val
                            # Also make output easily accessible via flat context
                            if isinstance(output_val, dict):
                                context_data.update(output_val)
                            
                            await session.commit()
                            break  # Success
                        
                        except Exception as e:
                            run.logs += f"Error in step '{step_name}': {str(e)}\n"
                            if attempt == WorkflowExecutorService.MAX_RETRIES:
                                if fallback_value is not None:
                                    run.logs += f"Step '{step_name}' failed after {WorkflowExecutorService.MAX_RETRIES} attempts. Using fallback value: {fallback_value}\n"
                                    context_data[step_name] = fallback_value
                                    await session.commit()
                                    break # Recovered with fallback
                                else:
                                    raise Exception(f"Step '{step_name}' failed after {WorkflowExecutorService.MAX_RETRIES} attempts without fallback. Last error: {str(e)}")
                            
                            backoff_time = 2 ** attempt
                            run.logs += f"Retrying in {backoff_time} seconds...\n"
                            await session.commit()
                            await asyncio.sleep(backoff_time)

                run.status = WorkflowRunStatus.COMPLETED
                run.logs += f"Workflow execution completed successfully. Total Tokens Used: {run.total_tokens}\n"
            
            except Exception as e:
                run.status = WorkflowRunStatus.FAILED
                run.logs += f"Workflow failed with error: {str(e)}\n"
            
            finally:
                await session.commit()
