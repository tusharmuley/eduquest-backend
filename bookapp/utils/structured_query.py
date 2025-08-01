# ✅ Simplified LLM Prompt + Query Handler for Structured Excel Data (bookapp_bookstructureddata)

from django.db import connection
from .llm_client import generate_answer
import re
from bookapp.models import Book
import traceback
import sys

def extract_sql_only(llm_output: str) -> str:
    match = re.search(r"```sql(.*?)```", llm_output, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    idx = llm_output.lower().find("select")
    if idx != -1:
        return llm_output[idx:].strip()
    return llm_output.strip()

def query_structured_data(book_id: int, user_prompt: str) -> str:
    try:
        prompt_lower = user_prompt.lower()

        with connection.cursor() as cursor:
            book = Book.objects.get(id=book_id)

            # 🧠 LLM Prompt
            sql_prompt = f"""
            You are a precise SQL assistant for a PostgreSQL table `bookapp_bookstructureddata`.

            Each Excel row is stored as multiple rows in this table:
            - book_id (int)
            - row_index (int)
            - column_name (text)
            - value (text)

            👉 Use:
            - `ILIKE` for fuzzy matches
            - `JOIN ON row_index` to combine filters (e.g. Year + Cost)
            - `book_id = {book_id}` in every query
            - `value::numeric` for numeric filters or aggregations
            - Only return clean SQL (no markdown, no explanation)

            Some examples:

            1. Count total patients:
            SELECT COUNT(DISTINCT value)
            FROM bookapp_bookstructureddata
            WHERE book_id = {book_id} AND column_name ILIKE '%patient_id%';

            2. Total treatment cost for Diabetes:
            SELECT SUM(cost.value::numeric)
            FROM (
            SELECT row_index FROM bookapp_bookstructureddata
            WHERE book_id = {book_id} AND column_name ILIKE '%diagnosis%' AND value ILIKE '%diabetes%'
            ) AS diag
            JOIN (
            SELECT row_index, value FROM bookapp_bookstructureddata
            WHERE book_id = {book_id} AND column_name ILIKE '%treatment_cost%'
            ) AS cost ON diag.row_index = cost.row_index;

            3. Average age of patients with Asthma:
            SELECT AVG(age.value::numeric)
            FROM (
            SELECT row_index FROM bookapp_bookstructureddata
            WHERE book_id = {book_id} AND column_name ILIKE '%diagnosis%' AND value ILIKE '%asthma%'
            ) AS diag
            JOIN (
            SELECT row_index, value FROM bookapp_bookstructureddata
            WHERE book_id = {book_id} AND column_name ILIKE '%age%'
            ) AS age ON diag.row_index = age.row_index;

            4. Patients treated in 2015:
            SELECT COUNT(DISTINCT value)
            FROM (
            SELECT row_index FROM bookapp_bookstructureddata
            WHERE book_id = {book_id} AND column_name ILIKE '%year%' AND value ILIKE '%2015%'
            ) AS yr
            JOIN (
            SELECT row_index, value FROM bookapp_bookstructureddata
            WHERE book_id = {book_id} AND column_name ILIKE '%patient_id%'
            ) AS pid ON yr.row_index = pid.row_index;

            User prompt: "{user_prompt}"
            """

            print("🔍 Prompt:", user_prompt)
            print("📘 Book ID:", book_id)

            raw_response = generate_answer(sql_prompt)
            print("🧾 LLM raw:\n", raw_response)

            sql_query = extract_sql_only(raw_response)
            print("✅ Cleaned SQL:\n", sql_query)

            if not sql_query.lower().startswith("select"):
                return f"❌ Invalid SQL:\n\n{sql_query}"

            cursor.execute(sql_query)
            rows = cursor.fetchall()
            colnames = [desc[0] for desc in cursor.description]

            print("📊 Rows returned:", rows)

            if not rows:
                return "⚠️ No matching results found."

            # Format response
            if len(rows[0]) == 1:
                val = rows[0][0]
                try:
                    num_val = float(val)
                    if any(w in prompt_lower for w in ["how many", "count", "number"]):
                        return f"👥 Total: {int(num_val)}"
                    elif any(w in prompt_lower for w in ["total", "cost", "spent"]):
                        return f"💰 Total: ₹{num_val:,.2f}"
                    elif "average" in prompt_lower:
                        return f"📊 Average: {num_val:.2f}"
                    else:
                        return f"✅ Result: {val}"
                except:
                    return f"✅ Result: {val}"

            # Table-style result
            table = [colnames] + [list(map(str, row)) for row in rows]
            formatted = "\n".join([" | ".join(row) for row in table[:20]])
            return f"📋 Results:\n\n{formatted}"

    except Exception as e:
        exc_type, exc_obj, tb = sys.exc_info()
        fname = tb.tb_frame.f_code.co_filename
        line_no = tb.tb_lineno
        traceback.print_exc()
        return f"❌ Error executing structured query: {e}, at {fname}:{line_no}"


    
