# Editra Operation DSL

Recommended operation types:

- ADD_SECTION
- REMOVE_SECTION
- UPDATE_SECTION
- ADD_SLIDE
- DELETE_SLIDE
- UPDATE_SLIDE
- REWRITE_TEXT
- CHANGE_TONE
- UPDATE_TABLE
- ADD_IMAGE
- UPDATE_IMAGE
- RESEARCH_UPDATE
- CONVERT_FORMAT

Every edit should ideally resolve to:

{
  "artifact_id": "...",
  "base_version": 3,
  "operation": "UPDATE_SLIDE",
  "target": "slide_5",
  "changes": {...},
  "preserve_style": true,
  "preserve_structure": true
}

This prevents every conversational request from becoming a full uncontrolled regeneration.
