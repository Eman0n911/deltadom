"""Preserve full read results for the next Browser Use model request.

Browser Use is optional. This adapter accepts its ActionResult object; it does
not interpret content, add evidence, or remove the native context size limit.
"""

import json


def attach_readback(result, receipt):
    """Preserve native action fields and deliver separately labelled UI evidence."""
    payload = json.dumps({"action_result": result.model_dump(exclude_none=True),
                          "post_action_readback": receipt}, ensure_ascii=False)
    return result.model_copy(update={"extracted_content": payload,
                                     "include_extracted_content_only_once": True})


def deliver_read_evidence(result):
    """Keep the short memory and request one-time delivery of the full read.

    In the observed 0.13.11 message manager, supplying long_term_memory alongside
    extracted_content without the one-time flag drops the latter from the next
    model message. Return a copy to preserve the original tool result for audit.
    """
    if (result.extracted_content and result.long_term_memory
            and not result.include_extracted_content_only_once):
        return result.model_copy(update={"include_extracted_content_only_once": True})
    return result
