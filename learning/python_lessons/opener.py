# First Principles: Python + SQL in one file
# Run with: python3 opener.py
# Uses only Python standard library, no install needed.

# --- PYTHON 1: names point to values ---
x = 5            # int
name = "ada"     # str
print(x, name, type(x))

# --- PYTHON 2: collections hold many values ---
nums = [1, 2, 3]              # list: ordered, changeable
person = {"id": 1, "name": "ada"}  # dict: key -> value
print(len(nums), nums[0], person["name"])

# --- PYTHON 3: code branches and loops ---
if x > 3:
    print("x is big")
for n in nums:
    print("n:", n)

# --- PYTHON 4: functions package reusable logic ---
def double(n):
    return n * 2

print(double(5))

# --- SQL 1: data lives in TABLES (rows + columns) ---
# Table people: | id INTEGER | name TEXT |
# Row = one fact. Column = one attribute.
import sqlite3

con = sqlite3.connect(":memory:")  # in-memory DB, no server
cur = con.cursor()
cur.execute("CREATE TABLE people(id INTEGER, name TEXT)")

# --- SQL 2: INSERT adds, SELECT asks ---
cur.execute("INSERT INTO people VALUES (1, 'ada')")
cur.execute("INSERT INTO people VALUES (2, 'grace')")
cur.execute("INSERT INTO people VALUES (3, 'termite')")

# SELECT columns FROM table WHERE filter
for row in cur.execute("SELECT * FROM people"):
    print(row)

for row in cur.execute("SELECT name FROM people WHERE id = 3"):
    print("found:", row)

con.close()
print("done - you ran Python that created SQL, wrote, and queried it.")
