from ..config import TAVILY_API_KEY


class ResearchAgent:
    """Web research agent with safe Tavily query sizing.

    Tavily currently limits search queries to 1500 characters. Uploaded
    documents can be much larger, so callers may provide long context. We
    keep the actual search query compact while preserving the user's intent
    and enough document context to make the research relevant.
    """

    MAX_QUERY_LENGTH = 1400

    def _build_query(self, query):
        query = (query or "").strip()
        if len(query) <= self.MAX_QUERY_LENGTH:
            return query

        # Prefer the beginning because it normally contains the user's
        # actual instruction. Keep the request safely below Tavily's 1500
        # character hard limit.
        return query[: self.MAX_QUERY_LENGTH].rstrip()

    def search(self, query):
        if not TAVILY_API_KEY:
            return {
                "results": [],
                "message": "Web research disabled: TAVILY_API_KEY is not configured.",
            }

        search_query = self._build_query(query)
        if not search_query:
            return {"results": []}

        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=TAVILY_API_KEY)
            response = client.search(
                query=search_query,
                max_results=5,
            )

            return {
                "results": [
                    {
                        "title": x.get("title", ""),
                        "url": x.get("url", ""),
                        "content": x.get("content", ""),
                    }
                    for x in response.get("results", [])
                ]
            }

        except Exception as exc:
            # Web research is an optional enhancement. A Tavily failure
            # must not prevent document/PPT generation from continuing.
            return {
                "results": [],
                "message": f"Web research skipped: {exc}",
            }
