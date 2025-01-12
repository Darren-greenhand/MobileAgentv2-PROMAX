import requests
import csv

url = "http://10.0.1.16:5408/caseGen"
headers = {
    "Content-Type": "application/json"
}
data = {
    "module": "",
    "demand": "manage multiple email accounts",
    "business_rules": "",
    "test_data": "",
    "samples": ""
}

response = requests.post(url, headers=headers, json=data)

print("Status Code:", response.status_code)

response_data = response.json()
analysis = eval(response_data["analysis"]) # 步骤列表
response = eval(response_data["response"]) # 响应列表，20个测试样例，'Module', 'Test Case Name', 'Preconditions', 'Test Data', 'Test Steps', 'Expected Results', 'Importance'

with open("results.csv", "w", newline='') as csvfile:
    writer = csv.writer(csvfile)
    
    # 写入分析步骤
    writer.writerow(["分析步骤"])
    writer.writerow([str(analysis)])  # 将分析步骤作为一行写入

    # 写入测试响应的表头
    writer.writerow(["Test Case Name"])
    
    # 写入每个测试样例
    for case in response:
        writer.writerow([case['Test Case Name']])




