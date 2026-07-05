import time
from typing import List, Dict, Any, Optional
from notion_client import Client
from notion_client.errors import APIResponseError
from notion_sync.logger import logger

class NotionSyncClient:
    def __init__(self, token: str):
        self.client = Client(auth=token)
        self.database_titles: Dict[str, str] = {}

    def execute_with_retry(self, api_func, *args, **kwargs) -> Any:
        """
        Executes a Notion API function with retries and exponential backoff.
        Handles API rate limits (HTTP 429) using the Retry-After header.
        """
        max_retries = 5
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                return api_func(*args, **kwargs)
            except APIResponseError as e:
                # HTTP 429 Too Many Requests
                if e.status == 429:
                    # Get retry-after header if present, else exponential backoff
                    retry_after = e.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else (base_delay * (2 ** attempt))
                    logger.warning(f"Notion API rate limited. Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                elif e.status >= 500:
                    # Server errors
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Notion API server error ({e.status}). Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                else:
                    # Client errors (400, 401, 403, 404, etc.) are generally not retried
                    logger.error(f"Notion API error (status={e.status}): {str(e)}")
                    raise e
            except Exception as e:
                # Network failures/timeouts
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Network error: {e}. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
                
        # Final attempt
        return api_func(*args, **kwargs)

    def query_database_or_datasource(self, db_id: str, start_cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves a page of results from a database, automatically resolving whether
        it is a standard database or a data-source-backed database.
        """
        clean_db_id = db_id.replace("-", "")
        # Retrieve database details to check for data_sources
        db_details = self.execute_with_retry(
            self.client.request,
            path=f"databases/{clean_db_id}",
            method="GET"
        )
        
        # Save title to mapping for directory path resolution
        db_title_list = db_details.get("title", [])
        db_title = db_title_list[0].get("plain_text", "Database") if db_title_list else "Database"
        self.database_titles[clean_db_id] = db_title
        
        data_sources = db_details.get("data_sources", [])
        if data_sources:
            ds_id = data_sources[0]["id"].replace("-", "")
            logger.info(f"Querying synced database '{db_title}' via Data Source...")
            
            body = {}
            if start_cursor:
                body["start_cursor"] = start_cursor
                
            return self.execute_with_retry(
                self.client.request,
                path=f"data_sources/{ds_id}/query",
                method="POST",
                body=body
            )
        else:
            logger.info(f"Querying standard database '{db_title}'...")
            
            body = {}
            if start_cursor:
                body["start_cursor"] = start_cursor
                
            return self.execute_with_retry(
                self.client.request,
                path=f"databases/{clean_db_id}/query",
                method="POST",
                body=body
            )

    def get_database_pages(self, database_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all pages under the target ID.
        Supports both Database IDs (by querying the database) and Page IDs (by fetching child_page/child_database blocks).
        """
        pages = []
        clean_db_id = database_id.replace("-", "")
        
        try:
            has_more = True
            start_cursor = None
            while has_more:
                response = self.query_database_or_datasource(clean_db_id, start_cursor)
                pages.extend(response.get("results", []))
                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")
                
            logger.info(f"Found {len(pages)} pages in the database.")
            return pages
            
        except APIResponseError as e:
            # If the ID is a page instead of a database, Notion API returns 400 Bad Request
            if e.status in (400, 404):
                logger.info("ID is not a database. Attempting to retrieve as a Page containing subpages/databases...")
                return self.get_page_subpages(clean_db_id)
            raise e

    def get_page_subpages(self, page_id: str) -> List[Dict[str, Any]]:
        """
        Fetches all subpages (child_page blocks) and pages inside nested databases (child_database blocks) under a root Page ID.
        """
        clean_page_id = page_id.replace("-", "")
        try:
            self.execute_with_retry(self.client.pages.retrieve, page_id=clean_page_id)
        except Exception as e:
            logger.error(f"Failed to retrieve root Page/Database: {e}")
            raise e
            
        subpages = []
        try:
            children = self.get_block_children(clean_page_id)
            for child in children:
                child_type = child.get("type")
                if child_type == "child_page":
                    subpage_id = child["id"].replace("-", "")
                    try:
                        subpage = self.execute_with_retry(self.client.pages.retrieve, page_id=subpage_id)
                        subpages.append(subpage)
                    except Exception as e:
                        logger.warning(f"Failed to retrieve subpage details for {subpage_id}: {e}")
                elif child_type == "child_database":
                    db_id = child["id"].replace("-", "")
                    try:
                        has_more = True
                        start_cursor = None
                        while has_more:
                            response = self.query_database_or_datasource(db_id, start_cursor)
                            results = response.get("results", [])
                            subpages.extend(results)
                            has_more = response.get("has_more", False)
                            start_cursor = response.get("next_cursor")
                    except Exception as e:
                        logger.warning(f"Failed to query nested database {db_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to retrieve child blocks of the root page: {e}")
            raise e
            
        logger.info(f"Found {len(subpages)} sub-pages/database items under the root page.")
        return subpages

    def get_block_children(self, block_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves the direct children of a block (with pagination).
        """
        children = []
        has_more = True
        start_cursor = None
        
        while has_more:
            kwargs = {"block_id": block_id}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
                
            response = self.execute_with_retry(
                self.client.blocks.children.list,
                **kwargs
            )
            
            children.extend(response.get("results", []))
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
            
        return children

    def get_block_children_recursive(self, block_id: str) -> List[Dict[str, Any]]:
        """
        Recursively retrieves all children blocks, building a nested block structure.
        """
        children = self.get_block_children(block_id)
        
        for child in children:
            if child.get("has_children", False):
                # Recursively fetch children and attach to the child dict
                child["children"] = self.get_block_children_recursive(child["id"])
                
        return children

    def get_page_title(self, page: Dict[str, Any]) -> str:
        """
        Helper to extract the page title from a page object.
        """
        properties = page.get("properties", {})
        
        # Look for the 'title' property type
        for prop_name, prop_val in properties.items():
            if prop_val.get("type") == "title":
                title_list = prop_val.get("title", [])
                if title_list:
                    return "".join([t.get("plain_text", "") for t in title_list])
                break
                
        # Fallback if no title property or empty
        return "Untitled Page"
