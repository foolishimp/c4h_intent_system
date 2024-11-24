"""
Test script to verify LiteLLM with Anthropic
test_litellm.py
"""
import os
from litellm import completion

def test_litellm():
    try:
        # Get key from environment
        key = os.getenv('ANTHROPIC_API_KEY')
        if not key:
            print("❌ ANTHROPIC_API_KEY not found in environment")
            return
            
        # Test completion
        response = completion(
            model="claude-3-opus-20240229",
            messages=[{
                "role": "user",
                "content": "Say hello!"
            }],
            api_key=key
        )
        
        print(f"✅ LiteLLM works! Response: {response.choices[0].message.content}")
        
    except Exception as e:
        print(f"❌ LiteLLM test failed: {str(e)}")

if __name__ == "__main__":
    test_litellm()