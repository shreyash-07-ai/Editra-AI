from ..config import TAVILY_API_KEY

class ResearchAgent:
    def search(self, query):
        if not TAVILY_API_KEY:
            return {"results": [], "message":"Web research disabled: TAVILY_API_KEY is not configured."}
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        r = client.search(query=query, max_results=5)
        return {
            "results":[
                {"title":x.get("title",""),"url":x.get("url",""),"content":x.get("content","")}
                for x in r.get("results",[])
            ]
        }
