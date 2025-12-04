# Privacy Views - Concrete Example

## Scenario
**User:** Regular user with `buid = 61478657`  
**Query:** "Query my grade for HW1"

---

## Step 1: Original Database Tables

### `user_information` table:
```
username          | password  | buid    | Student_Name | role
------------------|-----------|---------|--------------|------
alex@edu.com      | secret123 | 61478657| Alex Smith   | user
admin@edu.com     | admin456  | 99999999| Admin User   | admin
```

### `student_homeworks` table:
```
student_id | homework_id | grade
-----------|-------------|-------
61478657   | HW1         | 85.5
61478657   | HW2         | 92.0
64678953   | HW1         | 78.0
64678953   | HW2         | 88.5
```

### `student_information` table:
```
buid    | name        | email
--------|-------------|------------------
61478657| Alex Smith  | alex@university.edu
64678953| Jane Doe    | jane@university.edu
```

---

## Step 2: View Creation (Before Query)

The system creates these views in the database:

### For Regular Users:
```sql
CREATE OR REPLACE VIEW user_information_secure AS
SELECT 
    '***' as username,
    '***' as password,
    '***' as buid,
    Student_Name
FROM user_information;
```

**Result:** The view `user_information_secure` now contains:
```
username | password | buid | Student_Name
---------|----------|------|-------------
***      | ***      | ***  | Alex Smith
***      | ***      | ***  | Admin User
```

```sql
CREATE OR REPLACE VIEW student_information_secure AS
SELECT 
    buid as student_id,
    name,
    '***' as email
FROM student_information;
```

**Result:** The view `student_information_secure` now contains:
```
student_id | name       | email
-----------|------------|-------
61478657   | Alex Smith | ***
64678953   | Jane Doe   | ***
```

---

## Step 3: Query Generation

The LLM generates this SQL:
```sql
SELECT grade 
FROM student_homeworks 
WHERE homework_id = 'HW1'
```

---

## Step 4: Query Modification

The privacy system modifies the query:

1. **Checks if views are needed:** Query doesn't use `user_information` or `student_information`, so no view replacement needed
2. **Adds student_id filter** (for non-admin users):
```sql
SELECT grade 
FROM student_homeworks 
WHERE student_id = 61478657 AND homework_id = 'HW1'
```

---

## Step 5: Query Execution

The modified query runs against the database:
```sql
SELECT grade 
FROM student_homeworks 
WHERE student_id = 61478657 AND homework_id = 'HW1'
```

**Result:**
```json
[
  {
    "grade": 85.5
  }
]
```

---

## Step 6: Authorization Check

The system checks:
- ✅ User `61478657` is querying their own data (`student_id = 61478657`)
- ✅ Query is authorized

---

## Step 7: Result Filtering

The system verifies the results:
- ✅ All rows have `student_id = 61478657` (user's own data)
- ✅ No sensitive data leaked (query didn't access sensitive tables)

**Final Result:**
```json
{
  "reply": "Your grade for HW1 is 85.5"
}
```

---

## Example 2: What If User Tries to Query Someone Else's Data?

**Query:** "Query the grade for HW1 of buid 64678953"

### Step 1: Query Generation
```sql
SELECT grade 
FROM student_homeworks 
WHERE homework_id = 'HW1' AND student_id = 64678953
```

### Step 2: Query Modification
The privacy system detects `student_id = 64678953` is already in the query, so it doesn't add another filter.

### Step 3: Authorization Check
```python
# In privacy_system.check_authorization()
requested_buid = 64678953
caller_buid = 61478657

if requested_buid != caller_buid:
    return False, "Sorry, you are not allowed to see that."
```

**Result:**
```json
{
  "reply": "Sorry, you are not allowed to see that. You can only query your own data."
}
```

---

## Example 3: Query That Uses Views

**Query:** "Show me all student information"

### Step 1: Query Generation
```sql
SELECT * FROM student_information
```

### Step 2: Query Modification
The system replaces the table name with the view:
```sql
SELECT * FROM student_information_secure
```

### Step 3: Query Execution
The query runs against the view, which automatically masks `email`:
```json
[
  {
    "student_id": 61478657,
    "name": "Alex Smith",
    "email": "***"  // ← Automatically masked by the view!
  },
  {
    "student_id": 64678953,
    "name": "Jane Doe",
    "email": "***"  // ← Automatically masked by the view!
  }
]
```

### Step 4: Authorization Check
- ❌ User `61478657` is trying to see ALL students (not just their own)
- ❌ Query is blocked

**Result:**
```json
{
  "reply": "Sorry, you are not allowed to see that. You can only query your own data."
}
```

---

## Example 4: Admin User Query

**User:** Admin with `buid = 99999999`, `role = 'admin'`  
**Query:** "Show me all student information"

### Step 1: View Creation (Different for Admin)
```sql
CREATE OR REPLACE VIEW user_information_secure AS
SELECT 
    username,        -- Admins can see this
    '***' as password,
    buid,            -- Admins can see this
    Student_Name
FROM user_information;
```

### Step 2: Query Generation
```sql
SELECT * FROM student_information
```

### Step 3: Query Modification
```sql
SELECT * FROM student_information_secure
```
(No `student_id` filter added because user is admin)

### Step 4: Query Execution
```json
[
  {
    "student_id": 61478657,
    "name": "Alex Smith",
    "email": "***"  // Still masked even for admins
  },
  {
    "student_id": 64678953,
    "name": "Jane Doe",
    "email": "***"  // Still masked even for admins
  }
]
```

### Step 5: Authorization Check
- ✅ Admin user - authorization granted
- ✅ Query proceeds

**Result:**
```json
{
  "reply": "Here are all students: Alex Smith (ID: 61478657), Jane Doe (ID: 64678953)"
}
```

---

## Key Takeaways

1. **Views mask sensitive columns automatically** - No matter what query is written, sensitive data is protected
2. **Row-level filtering happens in application code** - Views don't filter rows, the privacy system adds WHERE clauses
3. **Defense in depth** - Multiple layers of protection (views, query modification, authorization checks)
4. **Transparent to queries** - The view looks like a regular table, but protects data automatically

