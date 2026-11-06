from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import duckdb
import os
import time
import json
import traceback

app = FastAPI(title="1CMR-API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration ---
HF_TOKEN = os.getenv("hf_token") 
BUCKET_BASE_URL = "https://huggingface.co/buckets/avezattar/1CMR-compact-bucket/resolve/main"

FILE_LIST = [f"{BUCKET_BASE_URL}/icmr_part0{i}.parquet" for i in range(1, 5)]

@app.get("/")
def root():
    return {"status": "online", "message": "1CMR API is Live (DuckDB)."}

@app.get("/search")
def search(mobile: str = Query(..., description="10-digit mobile number")):
    start_time = time.time()
    
    try:
        if len(mobile) != 10 or not mobile.isdigit():
            return Response(
                content=json.dumps({"error": "Please provide a valid 10-digit mobile number."}, indent=4), 
                media_type="application/json"
            )

        # Initialize DuckDB connection
        con = duckdb.connect(database=':memory:')
        
        # FIX: Set the home directory to /tmp (writable in Vercel)
        con.execute("SET home_directory='/tmp';")
        
        # FIX: Install and load httpfs extension explicitly
        # This is required to read files via https://
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")
        
        # If the files are in a private bucket, set the Bearer token
        if HF_TOKEN:
            # DuckDB uses HTTP secrets to attach headers to outgoing requests
            con.execute(f"""
                CREATE SECRET hf_secret (
                    TYPE HTTP,
                    EXTRA_HTTP_HEADERS MAP {{'Authorization': 'Bearer {HF_TOKEN}'}}
                );
            """)
        
        # Query the dataset directly over HTTP
        query = f"""
            SELECT name, fathersName AS father_name, phoneNumber AS mobile, 
                   otherNumber AS alternate_mobile, passportNumber AS passport_number, 
                   aadharNumber AS aadhar_number, age, gender, address, 
                   district, pincode, state, town
            FROM read_parquet({FILE_LIST})
            WHERE phoneNumber = ?
            LIMIT 5
        """
        
        result = con.execute(query, [mobile]).fetchall()
        columns = [desc[0] for desc in con.description]
        raw_records = [dict(zip(columns, row)) for row in result]
        
        con.close()
        
        elapsed = time.time() - start_time
        
        response_data = {
            "meta": {
                "credits": "Made by Mr. Anonymous",
                "search_query": mobile,
                "total_records": len(raw_records),
                "execution_time": f"{elapsed:.3f}s"
            },
            "results": []
        }

        if not raw_records:
            response_data["message"] = "No record found in the database."
            return Response(
                content=json.dumps(response_data, indent=4), 
                media_type="application/json"
            )
            
        for i, row in enumerate(raw_records, 1):
            clean_row = {k: v for k, v in row.items() if v is not None}
            clean_row["result_id"] = i
            response_data["results"].append(clean_row)
            
        return Response(
            content=json.dumps(response_data, indent=4, default=str), 
            media_type="application/json"
        )
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"CRITICAL ERROR:\n{error_trace}")
        return Response(
            content=json.dumps({"error": f"Search failed: {str(e)}"}, indent=4), 
            media_type="application/json"
        )
