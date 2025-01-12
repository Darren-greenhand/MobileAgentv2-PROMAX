from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks
from modelscope import snapshot_download, AutoModelForCausalLM, AutoTokenizer, GenerationConfig

local_dir = '/shd/jcy/ckpt'
device = "cuda"

model_dir = snapshot_download('qwen/Qwen-VL-Chat', revision='v1.1.0',cache_dir=local_dir)
model = AutoModelForCausalLM.from_pretrained(model_dir, device_map=device, trust_remote_code=True).eval()

groundingdino_dir = snapshot_download('AI-ModelScope/GroundingDINO', revision='v1.0.0',cache_dir=local_dir)
groundingdino_model = pipeline('grounding-dino-task', model=groundingdino_dir)

dir1 = snapshot_download('damo/cv_resnet18_ocr-detection-line-level_damo',cache_dir=local_dir)
dir2 = snapshot_download('damo/cv_convnextTiny_ocr-recognition-document_damo', cache_dir=local_dir)

ocr_detection = pipeline(Tasks.ocr_detection, model=dir1,cache_dir=local_dir)
ocr_recognition = pipeline(Tasks.ocr_recognition, model=dir2,cache_dir=local_dir)