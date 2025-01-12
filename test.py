import base64
import requests

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def inference_chat(chat, model, api_url, token):    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    data = {
        "model": model,
        "messages": [],
        "max_tokens": 2048,
        'temperature': 0.0,
        "seed": 1234
    }

    for role, content in chat:
        data["messages"].append({"role": role, "content": content})

    while True:
        try:
            res = requests.post(api_url, headers=headers, json=data)
            res_json = res.json()
            res_content = res_json['choices'][0]['message']['content']
        except:
            print("Network Error:")
            try:
                print(res.json())
            except:
                print("Request Failed")
        else:
            break
    
    return res_content

def process_image_gpt(image, query,model,api_url,token):
    # Prepare the image and query in the format required by the GPT-4o model
    image = encode_image(image)

    chat = [['user',[
            {
                "type": "text", 
                "text": query
            },
            {
                "type": "image_url", 
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image}"
                }
            },
        ]]]

    # Call the inference_chat function with the prepared data
    response = inference_chat(chat, model, api_url, token)
    
    # Return the response text
    return response


# success
response = process_image_gpt("test.jpg", "What is this?", "gpt-4o", "https://api2.aigcbest.top/v1/chat/completions", "sk-xjclhZEjJm3SpErq117dA25cD87f44Cf84F06d869551002c")
print(response)
