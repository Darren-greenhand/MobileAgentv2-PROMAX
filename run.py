import os,json
import time
import copy,math
import torch
import shutil
from PIL import Image, ImageDraw
import xml.etree.ElementTree as ET

from MobileAgent.api import inference_chat, encode_image
from MobileAgent.text_localization import ocr
from MobileAgent.icon_localization import det
from MobileAgent.controller import get_screenshot, tap, slide, type, back, home,clear
from MobileAgent.prompt import get_action_prompt, get_reflect_prompt, get_memory_prompt, get_process_prompt
from MobileAgent.chat import init_action_chat, init_reflect_chat, init_memory_chat, add_response, add_response_two_image

from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks
from modelscope import snapshot_download, AutoModelForCausalLM, AutoTokenizer, GenerationConfig

from dashscope import MultiModalConversation
import dashscope
import concurrent

####################################### Edit your Setting #########################################
# Your ADB path
adb_path = "adb -s emulator-5556"

instructions = [
    'Please use Thunderbird to send an email to 1275972958@qq.com, and include the following message: "hello world!".',
    'Please open the email from 1275972958@qq.com in Thunderbird and use the reply feature to respond with the message: "Thank you for your email!".',
    'Please select an email from your inbox in Thunderbird and forward it to 1275972958@qq.com, including the message: "Please see the attached email.".',
    'Please select an email from your inbox in Thunderbird and mark it as important for easy reference later.',
    'Please use Thunderbird to check for new email messages and refresh your inbox to ensure you see the latest emails.',
    'Please use Thunderbird to delete the email titled "Delete Me" from your inbox',
    'Please use Thunderbird to send an email to 1275972958@qq.com, CC your colleague at colleague@example.com, and BCC your manager at manager@example.com, with the message: "This is a test email.".',
    'Please use Thunderbird to block all future emails from the address 1275972958@qq.com.',
    'Please use Thunderbird to mark an email as junk from 1275972958@qq.com to ensure it goes to the junk folder in the future.',
    'Please use Thunderbird to change the application theme to "Dark Mode" for a better visual experience.',
    'Please use Thunderbird to send an email to 1275972958@qq.com, and include the following message: "Please find the attached document." and attach the file named "report.pdf".'
]
local_dir = '/shd/jcy/ckpt'

# 参数修改区👇 ####################################################
gui_switch = True
testid = 1
logname = 'instruction' + '_' + str(testid) + '_GUI' if gui_switch else 'instruction' + '_' + str(testid)
# 参数修改区👆 ####################################################

instruction = instructions[testid-1]

if logname:
    log_dir = '/shd/jcy/project/Mobile-Agent-v2/logs/' + logname
else:
    log_dir = '/shd/jcy/project/Mobile-Agent-v2/logs/' + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

log_path = log_dir + '/log.txt'
ui_path = log_dir + '/ui.txt'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
else:
    shutil.rmtree(log_dir)
    os.makedirs(log_dir)


# Your GPT-4o API URL
API_url = "https://api2.aigcbest.top/v1/chat/completions"

# Your GPT-4o API Token
token = "sk-xjclhZEjJm3SpErq117dA25cD87f44Cf84F06d869551002c"

# caption_call_method = "api"
caption_call_method = "local"

# caption_model = "gpt-4o"
caption_model = "qwen-vl-chat"

add_info = "If you want to tap an icon of an app, use the action \"Open app\". If you want to exit an app, use the action \"Home\"\n"
add_info += "You need to pay attention to the icons of button-related classes and their possible functions according to the caption of the icon\n"
add_info += "When ADB Keyboard is available, it may be that you have just finished inputting in the previous step, and you need to consider whether to switch to another EditText\n"
reflection_switch = True
memory_switch = False
###################################################################################################

# 以json格式写入文件，indent=4表示缩进4个空格
def log2file(file_path, data):
    with open(file_path, 'a') as f:
        json.dump(data, f, indent=4)
        f.write('\n')

def parse_ui_dump(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    # 定义要去掉的属性
    attributes_to_remove = {'index', 'package', 'resource-id'}
    elements_list = []

    index = 0

    # 过滤
    for elem in root.iter():
        elem_attributes = elem.attrib
        filtered_attributes = {k: v for k, v in elem_attributes.items() if k not in attributes_to_remove}
        if 'text' not in filtered_attributes and 'content-desc' not in filtered_attributes:
            continue
        if 'text' in filtered_attributes and 'content-desc' in filtered_attributes and filtered_attributes['text'] == '' and filtered_attributes['content-desc'] == '':
            continue
        if filtered_attributes['class'] == 'android.view.View': # 或许可以过滤掉不是android.widget的元素？
            continue
        # 标号
        filtered_attributes = dict({'seq': index}, **{k: v for k, v in filtered_attributes.items() if k != 'index'})        
        index += 1

        elements_list.append(filtered_attributes)
    return elements_list

def get_all_files_in_folder(folder_path):
    file_list = []
    for file_name in os.listdir(folder_path):
        file_list.append(file_name)
    return file_list
def draw_coordinates_on_image(image_path, coordinates):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    point_size = 10
    for coord in coordinates:
        draw.ellipse((coord[0] - point_size, coord[1] - point_size, coord[0] + point_size, coord[1] + point_size), fill='red')
    output_image_path = './screenshot/output_image.png'
    image.save(output_image_path)
    return output_image_path
def crop(image, box, i):
    image = Image.open(image)
    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    if x1 >= x2-10 or y1 >= y2-10:
        return
    cropped_image = image.crop((x1, y1, x2, y2))
    cropped_image.save(f"./temp/{i}.jpg")
def generate_local(tokenizer, model, image_file, query):
    query = tokenizer.from_list_format([
        {'image': image_file},
        {'text': query},
    ])
    response, _ = model.chat(tokenizer, query=query, history=None)
    return response
# 提示api上的模型处理图片
def process_image(image, query):
    dashscope.api_key = qwen_api
    image = "file://" + image
    messages = [{
        'role': 'user',
        'content': [
            {
                'image': image
            },
            {
                'text': query
            },
        ]
    }]
    response = MultiModalConversation.call(model=caption_model, messages=messages)
    
    try:
        response = response['output']['choices'][0]['message']['content'][0]["text"]
    except:
        response = "This is an icon."
    
    return response
# 批量处理多个图片，以索引为键，描述为值存储
def generate_api(images, query):
    icon_map = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_image, image, query): i for i, image in enumerate(images)}
        
        for future in concurrent.futures.as_completed(futures):
            i = futures[future]
            response = future.result()
            icon_map[i + 1] = response
    
    return icon_map
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
def generate_api_gpt(images, query,model,api_url,token):
    icon_map = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_image_gpt, image, query,model,api_url,token): i for i, image in enumerate(images)}
        
        for future in concurrent.futures.as_completed(futures):
            i = futures[future]
            response = future.result()
            icon_map[i + 1] = response
    
    return icon_map
def merge_text_blocks(text_list, coordinates_list):
    merged_text_blocks = []
    merged_coordinates = []

    sorted_indices = sorted(range(len(coordinates_list)), key=lambda k: (coordinates_list[k][1], coordinates_list[k][0]))
    sorted_text_list = [text_list[i] for i in sorted_indices]
    sorted_coordinates_list = [coordinates_list[i] for i in sorted_indices]

    num_blocks = len(sorted_text_list)
    merge = [False] * num_blocks

    for i in range(num_blocks):
        if merge[i]:
            continue
        
        anchor = i
        
        group_text = [sorted_text_list[anchor]]
        group_coordinates = [sorted_coordinates_list[anchor]]

        for j in range(i+1, num_blocks):
            if merge[j]:
                continue

            if abs(sorted_coordinates_list[anchor][0] - sorted_coordinates_list[j][0]) < 10 and \
            sorted_coordinates_list[j][1] - sorted_coordinates_list[anchor][3] >= -10 and sorted_coordinates_list[j][1] - sorted_coordinates_list[anchor][3] < 30 and \
            abs(sorted_coordinates_list[anchor][3] - sorted_coordinates_list[anchor][1] - (sorted_coordinates_list[j][3] - sorted_coordinates_list[j][1])) < 10:
                group_text.append(sorted_text_list[j])
                group_coordinates.append(sorted_coordinates_list[j])
                merge[anchor] = True
                anchor = j
                merge[anchor] = True

        merged_text = "\n".join(group_text)
        min_x1 = min(group_coordinates, key=lambda x: x[0])[0]
        min_y1 = min(group_coordinates, key=lambda x: x[1])[1]
        max_x2 = max(group_coordinates, key=lambda x: x[2])[2]
        max_y2 = max(group_coordinates, key=lambda x: x[3])[3]

        merged_text_blocks.append(merged_text)
        merged_coordinates.append([min_x1, min_y1, max_x2, max_y2])

    return merged_text_blocks, merged_coordinates



def get_perception_infos(adb_path, screenshot_file,iter):
    get_screenshot(adb_path,log_dir,iter)

    xml_file = "/shd/jcy/project/Mobile-Agent-v2/ui_dump.xml"
    elements_list = parse_ui_dump(xml_file)

    
    width, height = Image.open(screenshot_file).size
    
    text, coordinates = ocr(screenshot_file, ocr_detection, ocr_recognition)
    text, coordinates = merge_text_blocks(text, coordinates)
    
    center_list = [[(coordinate[0]+coordinate[2])/2, (coordinate[1]+coordinate[3])/2] for coordinate in coordinates]
    draw_coordinates_on_image(screenshot_file, center_list)
    
    perception_infos = []
    for i in range(len(coordinates)):
        perception_info = {"text": "text: " + text[i], "coordinates": coordinates[i]}
        perception_infos.append(perception_info)
        
    coordinates = det(screenshot_file, "icon", groundingdino_model)
    
    for i in range(len(coordinates)):
        perception_info = {"text": "icon", "coordinates": coordinates[i]}
        perception_infos.append(perception_info)
        
    image_box = []
    image_id = []
    for i in range(len(perception_infos)):
        if perception_infos[i]['text'] == 'icon':
            image_box.append(perception_infos[i]['coordinates'])
            image_id.append(i)

    for i in range(len(image_box)):
        crop(screenshot_file, image_box[i], image_id[i])

    images = get_all_files_in_folder(temp_file)
    if len(images) > 0:
        images = sorted(images, key=lambda x: int(x.split('/')[-1].split('.')[0]))
        image_id = [int(image.split('/')[-1].split('.')[0]) for image in images]
        icon_map = {}
        prompt = 'This image is an icon from a phone screen. Please briefly describe the shape and color of this icon in one sentence.'
        if caption_call_method == "local":
            for i in range(len(images)):
                image_path = os.path.join(temp_file, images[i])
                icon_width, icon_height = Image.open(image_path).size
                if icon_height > 0.8 * height or icon_width * icon_height > 0.2 * width * height:
                    des = "None"
                else:
                    des = generate_local(tokenizer, model, image_path, prompt)
                icon_map[i+1] = des
        else:
            for i in range(len(images)):
                images[i] = os.path.join(temp_file, images[i])
            # icon_map = generate_api(images, prompt)
            icon_map = generate_api_gpt(images, prompt,caption_model,API_url,token)
        for i, j in zip(image_id, range(1, len(image_id)+1)):
            if icon_map.get(j):
                perception_infos[i]['text'] = "icon: " + icon_map[j]

    for i in range(len(perception_infos)):
        perception_infos[i]['coordinates'] = [int((perception_infos[i]['coordinates'][0]+perception_infos[i]['coordinates'][2])/2), int((perception_infos[i]['coordinates'][1]+perception_infos[i]['coordinates'][3])/2)]
    ocr_list = []
    index = 0
    for ui in perception_infos:
        ocr_list.append(str(index)+ ':'+ str({'co':ui['coordinates'],'text':ui['text']}))
        index += 1
    
    # new
    ui_prompts = ''
    seq = 0


    # 可以过滤下重复的ocr文本和icon？以及那种明显把图标解析成字母的。 TODO
    for clickable_info in perception_infos:
        pass
    # 找出 坐标距离相差在5以内的所有元素，保留第一个在text里包含'icon'的元素，其他的都去掉
    distance_limit = 5
    for i in range(len(perception_infos)):
        if 'icon' in perception_infos[i]['text']:
            for j in range(i+1, len(perception_infos)):
                if math.sqrt((perception_infos[i]['coordinates'][0] - perception_infos[j]['coordinates'][0])**2 + (perception_infos[i]['coordinates'][1] - perception_infos[j]['coordinates'][1])**2) < distance_limit:
                    # 去掉perception_infos[j]
                    print('distance')
                    print('icon:',perception_infos[i]['coordinates'],perception_infos[j]['coordinates'])
                    perception_infos[j]['text'] = ''
                    perception_infos[j]['coordinates'] = (0, 0)


    for clickable_info in perception_infos:
        if clickable_info['text'] != "" and clickable_info['text'] != "icon: None" and clickable_info['coordinates'] != (0, 0):
            ui_prompt = f"{clickable_info['coordinates']};{clickable_info['text']}\n"
            # for element in elements_list:
            #     element['visited'] = False

            for element in elements_list:
                if 'bounds' not in element:
                    continue
                min_size = width * height
                # point是[x,y]，element['bounds']是"[281,181][943,326]"字符串，需要转换成[x1,y1,x2,y2]的形式
                point = (clickable_info['coordinates'][0], clickable_info['coordinates'][1])
                bounds = element['bounds']
                bounds = bounds.replace('[', '').replace(']', ',').split(',')
                bounds = [int(bound) for bound in bounds if bound != '']
                size = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
                if bounds[0] < point[0] < bounds[2] and bounds[1] < point[1] < bounds[3] and size < min_size:
                    min_size = size
                    if element['content-desc'] == '':
                        element['content-desc'] = 'None'

                    # ui_prompt = f"{seq}:{clickable_info['coordinates']};{clickable_info['text']};{element['class']};{element['content-desc']};clickable:{element['clickable']};enabled:{element['enabled']}\n" 
                    ui_prompt = f"{clickable_info['coordinates']};{clickable_info['text']};class:{element['class']};content-desc:{element['content-desc']};clickable:{element['clickable']};enabled:{element['enabled']};focusable:{element['focusable']}\n" 

            ui_prompts += ui_prompt
            seq += 1

    return perception_infos, width, height, elements_list, ocr_list, ui_prompts









### Load caption model ###
device = "cuda" if torch.cuda.is_available() else "cpu"
torch.manual_seed(1234)
if caption_call_method == "local":
    if caption_model == "qwen-vl-chat":
        qwen_dir = snapshot_download('qwen/Qwen-VL-Chat', revision='v1.1.0',cache_dir=local_dir)
        model = AutoModelForCausalLM.from_pretrained(qwen_dir, device_map=device, trust_remote_code=True).eval()
        model.generation_config = GenerationConfig.from_pretrained(qwen_dir, trust_remote_code=True)
    elif caption_model == "qwen-vl-chat-int4":
        qwen_dir = snapshot_download("qwen/Qwen-VL-Chat-Int4", revision='v1.0.0',cache_dir=local_dir)
        model = AutoModelForCausalLM.from_pretrained(qwen_dir, device_map=device, trust_remote_code=True,use_safetensors=True).eval()
        model.generation_config = GenerationConfig.from_pretrained(qwen_dir, trust_remote_code=True, do_sample=False)
    else:
        print("If you choose local caption method, you must choose the caption model from \"Qwen-vl-chat\" and \"Qwen-vl-chat-int4\"")
        exit(0)
    tokenizer = AutoTokenizer.from_pretrained(qwen_dir, trust_remote_code=True)
elif caption_call_method == "api":
    pass
else:
    print("You must choose the caption model call function from \"local\" and \"api\"")
    exit(0)



### Load ocr and icon detection model ###
groundingdino_dir = snapshot_download('AI-ModelScope/GroundingDINO', revision='v1.0.0',cache_dir=local_dir)
groundingdino_model = pipeline('grounding-dino-task', model=groundingdino_dir)

dir1 = snapshot_download('damo/cv_resnet18_ocr-detection-line-level_damo',cache_dir=local_dir)
dir2 = snapshot_download('damo/cv_convnextTiny_ocr-recognition-document_damo', cache_dir=local_dir)

ocr_detection = pipeline(Tasks.ocr_detection, model=dir1,cache_dir=local_dir)
ocr_recognition = pipeline(Tasks.ocr_recognition, model=dir2,cache_dir=local_dir)


thought_history = []
summary_history = []
action_history = []
summary = ""
action = ""
completed_requirements = ""
memory = ""
insight = ""
temp_file = "temp"
screenshot = "screenshot"
if not os.path.exists(temp_file):
    os.mkdir(temp_file)
else:
    shutil.rmtree(temp_file)
    os.mkdir(temp_file)
if not os.path.exists(screenshot):
    os.mkdir(screenshot)
error_flag = False

log2file(log_path, {'Instruction':instruction,'Add_info':add_info,'call_method':caption_call_method,'caption_model':caption_model})
log2file(ui_path, {'Instruction':instruction,'Add_info':add_info,'call_method':caption_call_method,'caption_model':caption_model})







iter = 1
while True:
    if iter == 1:
        screenshot_file = "./screenshot/screenshot.jpg"
        perception_infos, width, height,elements_list,ocr_list,ui_prompts1 = get_perception_infos(adb_path, screenshot_file,iter)
        
        ui_list = ui_prompts1.split('\n')

        ui_result = {'seq':iter,'combined':ui_list,'ocr':ocr_list,'xml':elements_list}
        log2file(ui_path,ui_result)

        shutil.rmtree(temp_file)
        os.mkdir(temp_file)
        
        keyboard = False
        keyboard_height_limit = 0.9 * height
        for perception_info in perception_infos:
            if perception_info['coordinates'][1] < keyboard_height_limit:
                continue
            if 'ADB Keyboard' in perception_info['text']:
                keyboard = True
                break

    prompt_action = get_action_prompt(instruction,gui_switch, ui_prompts1,perception_infos, width, height, keyboard, summary_history, action_history, summary, action, add_info, error_flag, completed_requirements, memory)

    chat_action = init_action_chat()
    chat_action = add_response("user", prompt_action, chat_action, screenshot_file)

    output_action = inference_chat(chat_action, 'gpt-4o', API_url, token)
    thought = output_action.split("### Thought ###")[-1].split("### Action ###")[0].replace("\n", " ").replace(":", "").replace("  ", " ").strip()
    summary = output_action.split("### Operation ###")[-1].replace("\n", " ").replace("  ", " ").strip()
    action = output_action.split("### Action ###")[-1].split("### Operation ###")[0].replace("\n", " ").replace("  ", " ").strip()
    chat_action = add_response("assistant", output_action, chat_action)
    status = "#" * 50 + " Decision " + "#" * 50
    print(status)
    print(output_action)
    
    log_data = {}

    if memory_switch:
        prompt_memory = get_memory_prompt(insight)
        chat_action = add_response("user", prompt_memory, chat_action)
        output_memory = inference_chat(chat_action, 'gpt-4o', API_url, token)
        chat_action = add_response("assistant", output_memory, chat_action)
        status = "#" * 50 + " Memory " + "#" * 50
        print(status)
        print(output_memory)
        print('#' * len(status))
        output_memory = output_memory.split("### Important content ###")[-1].split("\n\n")[0].strip() + "\n"
        if "None" not in output_memory and output_memory not in memory:
            memory += output_memory
    
    if "Open app" in action:
        app_name = action.split("(")[-1].split(")")[0]
        text, coordinate = ocr(screenshot_file, ocr_detection, ocr_recognition)
        tap_coordinate = [0, 0]
        found = False
        for ti in range(len(text)):
            if app_name == text[ti]:
                found = True
                name_coordinate = [int((coordinate[ti][0] + coordinate[ti][2])/2), int((coordinate[ti][1] + coordinate[ti][3])/2)]
                tap(adb_path, name_coordinate[0], name_coordinate[1]- int(coordinate[ti][3] - coordinate[ti][1]))# 
                print('Command: adb tap', name_coordinate[0], name_coordinate[1]- int(coordinate[ti][3] - coordinate[ti][1]))
                log_data = {'seq':iter,'completed_content':completed_requirements,'Action':action,'Thought':thought,'Summary':summary}
                break
        if not found:
            for ti in range(len(text)):
                if text[ti].replace(".", "") in app_name or app_name in text[ti].replace(".", ""):
                    name_coordinate = [int((coordinate[ti][0] + coordinate[ti][2])/2), int((coordinate[ti][1] + coordinate[ti][3])/2)]
                    tap(adb_path, name_coordinate[0], name_coordinate[1]- int(coordinate[ti][3] - coordinate[ti][1]))
                    print('Command: adb tap', name_coordinate[0], name_coordinate[1]- int(coordinate[ti][3] - coordinate[ti][1]))
                    log_data = {'seq':iter,'completed_content':completed_requirements,'Action':action,'Thought':thought,'Summary':summary}
                    break

    elif "Tap" in action:
        coordinate = action.split("(")[-1].split(")")[0].split(", ")
        x, y = int(coordinate[0]), int(coordinate[1])
        tap(adb_path, x, y)
        print('Command: adb tap', x, y)
        log_data = {'seq':iter,'completed_content':completed_requirements,'Action':action,'Thought':thought,'Summary':summary}
    
    elif "Swipe" in action:
        coordinate1 = action.split("Swipe (")[-1].split("), (")[0].split(", ")
        coordinate2 = action.split("), (")[-1].split(")")[0].split(", ")
        x1, y1 = int(coordinate1[0]), int(coordinate1[1])
        x2, y2 = int(coordinate2[0]), int(coordinate2[1])
        slide(adb_path, x1, y1, x2, y2)
        print('Command: adb swipe', x1, y1, x2, y2)
        log_data = {'seq':iter,'completed_content':completed_requirements,'Action':action,'Thought':thought,'Summary':summary}
        
    elif "Type" in action:
        if "(text)" not in action:
            text = action.split("(")[-1].split(")")[0]
        else:
            text = action.split(" \"")[-1].split("\"")[0]
        type(adb_path, text)
        log_data = {'seq':iter,'completed_content':completed_requirements,'Action':action,'Thought':thought,'Summary':summary}
    
    elif "Back" in action:
        back(adb_path)
        log_data = {'seq':iter,'completed_content':completed_requirements,'Action':action,'Thought':thought,'Summary':summary}
    
    elif "Home" in action:
        home(adb_path)

        log_data = {'seq':iter,'completed_content':completed_requirements,'Action':action,'Thought':thought,'Summary':summary}

    elif "Clear" in action:
        clear(adb_path)
        print('Command adb clean')
        log_data = {'seq':iter,'completed_content':completed_requirements,'Action':action,'Thought':thought,'Summary':summary}

    elif "Stop" in action:
        print('Found stop action, stopping the program.')
        log2file(log_path, {'seq':iter,'completed_content':completed_requirements,'Action':action,'Thought':thought,'Summary':summary})
        break
    print('#' * len(status))

    time.sleep(5)

    iter += 1
    
    last_perception_infos = copy.deepcopy(perception_infos)
    last_screenshot_file = "./screenshot/last_screenshot.jpg"
    last_keyboard = keyboard
    if os.path.exists(last_screenshot_file):
        os.remove(last_screenshot_file)
    os.rename(screenshot_file, last_screenshot_file)

    perception_infos, width, height,elements_list,ocr_list,ui_prompts2 = get_perception_infos(adb_path, screenshot_file,iter)
    ui_list = ui_prompts2.split('\n')
    ui_result = {'seq':iter,'combined':ui_list,'ocr':ocr_list,'xml':elements_list}
    log2file(ui_path,ui_result)
    shutil.rmtree(temp_file)
    os.mkdir(temp_file)
    
    keyboard = False
    for perception_info in perception_infos:
        if perception_info['coordinates'][1] < keyboard_height_limit:
            continue
        if 'ADB Keyboard' in perception_info['text']:
            keyboard = True
            break
    
    if reflection_switch:
        prompt_reflect = get_reflect_prompt(instruction, gui_switch,ui_prompts1,last_perception_infos, ui_prompts2,perception_infos, width, height, last_keyboard, keyboard, summary, action, add_info)
        chat_reflect0 = init_reflect_chat()
        chat_reflect = add_response_two_image("user", prompt_reflect, chat_reflect0, [last_screenshot_file, screenshot_file])

        output_reflect = inference_chat(chat_reflect, 'gpt-4o', API_url, token)
        reflect = output_reflect.split("### Answer ###")[-1].replace("\n", " ").strip()
        chat_reflect = add_response("assistant", output_reflect, chat_reflect)
        status = "#" * 50 + " Reflcetion " + "#" * 50
        print(status)
        print(output_reflect)
        print('#' * len(status))
        log_data['reflect'] = output_reflect
        log2file(log_path, log_data)
        if 'A' in reflect:
            thought_history.append(thought)
            summary_history.append(summary)
            action_history.append(action)
            
            prompt_planning = get_process_prompt(instruction, thought_history, summary_history, action_history, completed_requirements, add_info)
            chat_planning = init_memory_chat()
            chat_planning = add_response("user", prompt_planning, chat_planning)
            output_planning = inference_chat(chat_planning, 'gpt-4-turbo', API_url, token)
            chat_planning = add_response("assistant", output_planning, chat_planning)
            status = "#" * 50 + " Planning " + "#" * 50
            print(status)
            print(output_planning)
            print('#' * len(status))
            completed_requirements = output_planning.split("### Completed contents ###")[-1].replace("\n", " ").strip()
            error_flag = False
        
        elif 'B' in reflect:
            error_flag = True
            back(adb_path)
            
        elif 'C' in reflect:
            error_flag = True
    
    else:
        thought_history.append(thought)
        summary_history.append(summary)
        action_history.append(action)
        
        prompt_planning = get_process_prompt(instruction, thought_history, summary_history, action_history, completed_requirements, add_info)
        chat_planning = init_memory_chat()
        chat_planning = add_response("user", prompt_planning, chat_planning)
        output_planning = inference_chat(chat_planning, 'gpt-4-turbo', API_url, token)
        chat_planning = add_response("assistant", output_planning, chat_planning)
        status = "#" * 50 + " Planning " + "#" * 50
        print(status)
        print(output_planning)
        print('#' * len(status))
        completed_requirements = output_planning.split("### Completed contents ###")[-1].replace("\n", " ").strip()
         
    os.remove(last_screenshot_file)
