class EditingAgent:
    def operation_plan(self, prompt):
        p = prompt.lower()
        ops = []
        if "executive summary" in p: ops.append("add_executive_summary")
        if "slide" in p and ("add" in p or "create" in p): ops.append("add_slide")
        if "concise" in p or "shorter" in p: ops.append("rewrite_concise")
        if "tone" in p or "professional" in p: ops.append("change_tone")
        if not ops: ops.append("general_modify")
        return ops
