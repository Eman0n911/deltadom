"""Upstream Workflow Use semantic mapping capture and real deterministic executor."""
from workflow_use.schema.views import ClickStep
from workflow_use.workflow.semantic_executor import SemanticWorkflowExecutor
from workflow_use.workflow.semantic_extractor import SemanticExtractor


async def capture_workflow(browser_session,locator):
    page=await browser_session.get_current_page()
    mapping=await SemanticExtractor().extract_semantic_mapping(page)
    matches=[]
    for key,info in mapping.items():
        selector=info.get('hierarchical_selector') or info.get('selectors')
        try:
            same=await locator.evaluate('(e,selector)=>document.querySelector(selector)===e',selector)
        except Exception:  # noqa: BLE001 -- upstream selector may not be CSS
            same=False
        if same:matches.append((key,info))
    if len(matches)!=1:raise ValueError(f'upstream semantic mapping identifies selected element {len(matches)} times')
    key,info=matches[0]
    step=ClickStep(type='click',target_text=key,elementTag='button',
                   cssSelector=info.get('hierarchical_selector') or info['selectors'])
    return step,mapping


async def run_workflow(browser_session,step):
    executor=SemanticWorkflowExecutor(browser_session,max_retries=0)
    return await executor.execute_step(step)
