"""
Simple test script to verify Anthropic API key
test_anthropic_key.py
"""
import os
from anthropic import Anthropic

def test_key():
    try:
        # Get key from environment
        key = os.getenv('ANTHROPIC_API_KEY')
        if not key:
            print("❌ ANTHROPIC_API_KEY not found in environment")
            return
            
        # Initialize client
        client = Anthropic(api_key=key)
        
        # Simple test message
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=100,
            messages=[{
                "role": "user", 
                "content": "Say hello!"
            }]
        )
        
        print(f"✅ API key works! Response: {response.content}")
        
    except Exception as e:
        print(f"❌ API key test failed: {str(e)}")

if __name__ == "__main__":
    test_key()