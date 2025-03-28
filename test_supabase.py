import os
import sys
import logging
import dotenv
from time import time
from datetime import datetime
import uuid

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
dotenv.load_dotenv()

# Test Supabase connection
logger.info("Testing Supabase integration")

try:
    # Check Python version
    logger.info(f"Python version: {sys.version}")
    
    # Import Supabase client
    from supabase import create_client
    logger.info("✅ Supabase client library imported successfully")
    
    # Get credentials from environment
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error("❌ Supabase credentials not found in environment variables")
        sys.exit(1)
    
    logger.info(f"✅ SUPABASE_URL found: {supabase_url}")
    logger.info(f"✅ SUPABASE_KEY found: {supabase_key[:8]}...")
    
    # Initialize Supabase client
    supabase = create_client(supabase_url, supabase_key)
    logger.info("✅ Supabase client initialized successfully")
    
    # Test connection by querying the database
    logger.info("Testing database connection by querying generations table...")
    start_time = time()
    response = supabase.table('generations').select("*").limit(1).execute()
    request_duration = time() - start_time
    
    logger.info(f"✅ Database query successful! Response time: {request_duration:.2f} seconds")
    logger.info(f"Found {len(response.data)} records")
    
    # Test inserting a record
    logger.info("Testing database insertion...")
    test_id = str(uuid.uuid4())
    test_data = {
        'url': f"https://test-url-{test_id}.jpg",
        'content_type': 'creative-scene',
        'type': 'image',
        'prompt': 'Test prompt for Supabase integration',
        'created_at': datetime.now().isoformat()
    }
    
    start_time = time()
    insert_response = supabase.table('generations').insert(test_data).execute()
    request_duration = time() - start_time
    
    if insert_response.data:
        logger.info(f"✅ Database insertion successful! Response time: {request_duration:.2f} seconds")
        inserted_id = insert_response.data[0].get('id')
        logger.info(f"Inserted record ID: {inserted_id}")
        
        # Test retrieving the inserted record
        logger.info("Testing retrieval of inserted record...")
        fetch_response = supabase.table('generations').select("*").eq('id', inserted_id).execute()
        
        if fetch_response.data and len(fetch_response.data) > 0:
            logger.info(f"✅ Successfully retrieved the inserted record")
            
            # Test deleting the test record
            logger.info("Cleaning up by deleting the test record...")
            delete_response = supabase.table('generations').delete().eq('id', inserted_id).execute()
            
            if delete_response.data and len(delete_response.data) > 0:
                logger.info(f"✅ Successfully deleted the test record")
            else:
                logger.warning(f"⚠️ Could not delete the test record")
        else:
            logger.error(f"❌ Could not retrieve the inserted record")
    else:
        logger.error(f"❌ Database insertion failed")
        logger.error(f"Response: {insert_response}")
    
    logger.info("All Supabase tests completed!")
    
except ImportError as e:
    logger.error(f"❌ Failed to import Supabase client: {str(e)}")
    logger.error("Please ensure supabase-py is installed with: pip install supabase")
    sys.exit(1)
except Exception as e:
    logger.error(f"❌ Error during Supabase test: {str(e)}")
    sys.exit(1) 