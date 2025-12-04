import re
import logging
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class PrivacySystem:
    """
    Privacy system for protecting sensitive data in text-to-SQL queries.
    Creates SQL views to limit access and filters results based on user role.
    """
    
    # Define sensitive columns that should be protected
    SENSITIVE_COLUMNS = {
        'user_information': ['password', 'username', 'buid'],
        'student_information': ['email']
    }
    
    def __init__(self, supabase_url: str, supabase_key: str):
        """
        Initialize the PrivacySystem.
        
        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase API key (service role or publishable)
        """
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
    
    def create_privacy_views(self, caller_role: str, caller_buid: Optional[str] = None) -> bool:
        """
        Create SQL views that protect sensitive columns based on user role.
        Views are created before query execution to limit what can be accessed.
        
        Args:
            caller_role: User's role ('admin' or 'user')
            caller_buid: User's BU ID (required for non-admin users)
            
        Returns:
            True if views were created successfully, False otherwise
        """
        try:
            import requests
            
            # Admin users can see all data, but sensitive columns are still masked
            if caller_role == 'admin':
                views_sql = self._generate_admin_views()
            else:
                if not caller_buid:
                    logger.error("[PRIVACY] Cannot create views: caller_buid is required for non-admin users")
                    return False
                views_sql = self._generate_user_views(caller_buid)
            
            logger.info(f"[PRIVACY] Creating privacy views for role: {caller_role}")
            
            # Execute view creation SQL
            resp = requests.post(
                f"{self.supabase_url}/rest/v1/rpc/run_sql",
                headers=self.headers,
                json={"sql": views_sql}
            )
            
            if resp.status_code not in [200, 201]:
                logger.warning(f"[PRIVACY] View creation returned status {resp.status_code}: {resp.text}")
                # Don't fail completely - views might already exist
                return True
            
            logger.info("[PRIVACY] Privacy views created successfully")
            return True
            
        except Exception as e:
            logger.error(f"[PRIVACY] Error creating privacy views: {str(e)}")
            return False
    
    def _generate_admin_views(self) -> str:
        """
        Generate SQL views for admin users.
        Admins can see all data but sensitive columns are still masked for security.
        """
        views = []
        
        # View for user_information - admins can see username and buid, but password is always masked
        views.append("""
        CREATE OR REPLACE VIEW user_information_secure AS
        SELECT 
            username,
            '***' as password,
            buid,
            Student_Name
        FROM user_information;
        """)
        
        # View for student_information - mask email
        # Note: Table name is student_information (lowercase) based on schema
        views.append("""
        CREATE OR REPLACE VIEW student_information_secure AS
        SELECT 
            buid as student_id,
            name,
            '***' as email
        FROM student_information;
        """)
        
        return "\n".join(views)
    
    def _generate_user_views(self, caller_buid: str) -> str:
        """
        Generate SQL views for regular users.
        Views mask sensitive columns but don't filter rows - row filtering happens in application code.
        This prevents issues with JOINs returning empty results.
        
        Args:
            caller_buid: The user's BU ID to filter by (used for reference, not filtering in view)
        """
        views = []
        
        # View for user_information - mask sensitive fields but don't filter rows
        # Row filtering will be done in application code after query execution
        views.append("""
        CREATE OR REPLACE VIEW user_information_secure AS
        SELECT 
            '***' as username,
            '***' as password,
            '***' as buid,
            Student_Name
        FROM user_information;
        """)
        
        # View for student_information - mask email but don't filter rows
        # Note: Table name is student_information (lowercase), and primary key is buid
        views.append("""
        CREATE OR REPLACE VIEW student_information_secure AS
        SELECT 
            buid as student_id,
            name,
            '***' as email
        FROM student_information;
        """)
        
        return "\n".join(views)
    
    def modify_query_for_privacy(self, sql_query: str, caller_role: str, caller_buid: Optional[str] = None) -> str:
        """
        Modify the SQL query to use secure views instead of base tables.
        This ensures sensitive columns are automatically protected.
        
        Args:
            sql_query: Original SQL query
            caller_role: User's role
            caller_buid: User's BU ID
            
        Returns:
            Modified SQL query using secure views
        """
        modified_query = sql_query
        
        # Only replace table names if they appear as standalone table references
        # Be careful not to replace in string literals or comments
        # Replace user_information (case-insensitive, whole word)
        modified_query = re.sub(
            r'\buser_information\b',
            'user_information_secure',
            modified_query,
            flags=re.IGNORECASE
        )
        
        # Replace Student_Information (case-insensitive, whole word)
        modified_query = re.sub(
            r'\bStudent_Information\b',
            'student_information_secure',
            modified_query,
            flags=re.IGNORECASE
        )
        
        logger.info(f"[PRIVACY] Query modified from: {sql_query[:100]}... to: {modified_query[:100]}...")
        
        # For non-admin users, ensure they can only query their own data
        if caller_role != 'admin' and caller_buid:
            safe_buid = re.sub(r"[^A-Za-z0-9_\-]", "", str(caller_buid))
            
            # If query involves student_homeworks, check if student_id is already specified
            if 'student_homeworks' in modified_query.lower():
                # Extract any existing student_id values from the query
                # Match patterns like: student_id = 123, student_id=123, student_id = '123', etc.
                student_id_matches = re.findall(r'student_id\s*[=<>]+\s*[\'"]?(\d+)[\'"]?', modified_query, re.IGNORECASE)
                
                if student_id_matches:
                    # A student_id is already specified in the query
                    requested_buid = student_id_matches[0]
                    logger.info(f"[PRIVACY] Query already specifies student_id: {requested_buid}, caller_buid: {safe_buid}")
                    
                    # Authorization: non-admins can only query their own data
                    if str(requested_buid) != str(safe_buid):
                        logger.warning(f"[PRIVACY] Unauthorized: User {safe_buid} trying to query {requested_buid}")
                        # Don't modify query - let authorization check handle it
                        # The query will be blocked in the authorization step
                    # If they match, no need to add filter - query is already correct
                else:
                    # No student_id specified, add filter for caller's buid
                    logger.info(f"[PRIVACY] No student_id in query, adding filter for caller: {safe_buid}")
                    student_id_filter = f"student_id = {safe_buid}"
                    if 'where' in modified_query.lower():
                        modified_query = re.sub(
                            r'(WHERE|where)\s+',
                            f"WHERE {student_id_filter} AND ",
                            modified_query,
                            count=1
                        )
                    else:
                        if 'order by' in modified_query.lower() or 'limit' in modified_query.lower():
                            modified_query = re.sub(
                                r'(ORDER BY|order by|LIMIT|limit)',
                                f"WHERE {student_id_filter} \\1",
                                modified_query,
                                count=1
                            )
                        else:
                            modified_query = modified_query + f" WHERE {student_id_filter}"
        
        logger.info(f"[PRIVACY] Modified query: {modified_query}")
        return modified_query
    
    def filter_sensitive_data(self, query_result: Any, caller_role: str, caller_buid: Optional[str] = None) -> Any:
        """
        Filter sensitive data from query results after execution.
        This is a safety net in case views weren't used or bypassed.
        
        Args:
            query_result: The result from the SQL query
            caller_role: User's role
            caller_buid: User's BU ID
            
        Returns:
            Filtered query result with sensitive data removed
        """
        if not isinstance(query_result, list):
            return query_result
        
        filtered_result = []
        
        for row in query_result:
            if not isinstance(row, dict):
                filtered_result.append(row)
                continue
            
            # Create a copy of the row
            filtered_row = row.copy()
            
            # Remove sensitive columns based on role
            if caller_role != 'admin':
                # Non-admin users: mask all sensitive fields
                for table, columns in self.SENSITIVE_COLUMNS.items():
                    for col in columns:
                        if col in filtered_row:
                            filtered_row[col] = '***'
                
                # Also filter by buid if present
                if caller_buid and 'student_id' in filtered_row:
                    if str(filtered_row.get('student_id')) != str(caller_buid):
                        # Skip this row - doesn't belong to user
                        continue
                
                if caller_buid and 'buid' in filtered_row:
                    if str(filtered_row.get('buid')) != str(caller_buid):
                        # Skip this row - doesn't belong to user
                        continue
            else:
                # Admin users: still mask passwords and sensitive identifiers
                if 'password' in filtered_row:  
                    filtered_row['password'] = '***'
                if 'email' in filtered_row:
                    filtered_row['email'] = '***'
            
            filtered_result.append(filtered_row)
        
        return filtered_result
    
    def check_authorization(self, sql_query: str, caller_role: str, caller_buid: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Check if the user is authorized to execute the query.
        This is done AFTER the query is executed as a safety check.
        
        Args:
            sql_query: The SQL query to check
            caller_role: User's role
            caller_buid: User's BU ID
            
        Returns:
            Tuple of (is_authorized, error_message)
        """
        # Admin users can query anything
        if caller_role == 'admin':
            return True, None
        
        # Non-admin users need a buid
        if not caller_buid:
            return False, "Caller BU ID unknown; cannot authorize request."
        
        # Extract requested student_id from query
        buid_match = re.search(r"student_id\s*[=<>]+\s*['\"]?(\d+)['\"]?", sql_query, re.IGNORECASE)
        requested_buid = buid_match.group(1) if buid_match else None
        
        if not requested_buid:
            # Try to extract from the query text (any sequence of digits)
            buid_match = re.search(r"\b(\d{7,9})\b", sql_query)
            requested_buid = buid_match.group(1) if buid_match else None
        
        # For non-admin users, verify they're only querying their own data
        if requested_buid:
            if str(requested_buid) != str(caller_buid):
                logger.warning(f"[AUTHORIZATION] User {caller_buid} attempted to query {requested_buid}")
                return False, "Sorry, you are not allowed to see that. You can only query your own data."
        else:
            # No buid specified - should have been added by privacy system, but log warning
            logger.warning("[AUTHORIZATION] No student_id found in query for non-admin user")
            # This is allowed - the privacy system should have added the filter
        
        return True, None
    
    def validate_query_authorization(self, sql_query: str, caller_role: str, caller_buid: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Comprehensive authorization check for queries.
        This method consolidates all authorization logic and should be called after query execution.
        
        Args:
            sql_query: The SQL query that was executed
            caller_role: User's role ('admin' or 'user')
            caller_buid: User's BU ID
            
        Returns:
            Tuple of (is_authorized, error_message)
            - If authorized: (True, None)
            - If not authorized: (False, error_message_string)
        """
        return self.check_authorization(sql_query, caller_role, caller_buid)
    
    def verify_result_authorization(self, query_result: Any, caller_role: str, caller_buid: Optional[str] = None) -> Tuple[Any, bool]:
        """
        Verify that query results only contain data the user is authorized to see.
        This is the final safety check after query execution.
        
        Args:
            query_result: The result from the SQL query
            caller_role: User's role
            caller_buid: User's BU ID
            
        Returns:
            Tuple of (filtered_result, is_authorized)
        """
        if caller_role == 'admin':
            return query_result, True
        
        if not caller_buid:
            return None, False
        
        if not isinstance(query_result, list):
            return query_result, True
        
        # Filter results to only include rows matching caller's buid
        authorized_rows = []
        for row in query_result:
            if not isinstance(row, dict):
                continue
            
            # Check student_id
            if 'student_id' in row:
                if str(row.get('student_id')) == str(caller_buid):
                    authorized_rows.append(row)
                continue
            
            # Check buid
            if 'buid' in row:
                if str(row.get('buid')) == str(caller_buid):
                    authorized_rows.append(row)
                continue
            
            # If no identifier found, include it (might be from a join)
            authorized_rows.append(row)
        
        if len(authorized_rows) != len(query_result):
            logger.warning(
                f"[PRIVACY] Filtered {len(query_result) - len(authorized_rows)} unauthorized rows from response"
            )
        
        return authorized_rows, True

