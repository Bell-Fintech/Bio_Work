import streamlit as st
from PIL import Image
import io
import base64
import os
import time
import requests
import json
import uuid

# 设置页面标题
st.set_page_config(page_title="DNA作业批改", page_icon="🧬", layout="wide")


# 工具函数
def resize_image(image, max_size=1024):
    width, height = image.size
    if width > max_size or height > max_size:
        if width > height:
            new_width = max_size
            new_height = int(height * (max_size / width))
        else:
            new_height = max_size
            new_width = int(width * (max_size / height))
        image = image.resize((new_width, new_height), Image.LANCZOS)
    return image


def compress_image(image, quality=85):
    buffered = io.BytesIO()
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    image.save(buffered, format="JPEG", quality=quality, optimize=True)
    return Image.open(buffered)


def image_to_base64(image, max_size=1024, quality=85):
    image = resize_image(image, max_size)
    image = compress_image(image, quality)
    buffered = io.BytesIO()
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    image.save(buffered, format="JPEG", quality=quality)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str


# Cloudflare Worker 代理客户端
class CloudflareProxyClient:
    def __init__(self, api_key, proxy_url):
        self.api_key = api_key
        self.proxy_url = proxy_url
        self.chat = ChatCompletions(self)


class ChatCompletions:
    def __init__(self, client):
        self.client = client

    def create(self, model, messages, max_tokens=1500, **kwargs):
        """发送聊天补全请求到代理API"""
        try:
            # 准备数据
            payload = {
                "api_key": self.client.api_key,
                "endpoint": "chat/completions",
                "params": {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    **kwargs
                }
            }

            # 发送请求到代理
            response = requests.post(
                self.client.proxy_url,
                json=payload,
                timeout=120
            )

            # 检查错误
            if response.status_code != 200:
                error_msg = response.text
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        if isinstance(error_data["error"], dict):
                            error_msg = error_data["error"].get("message", str(error_data["error"]))
                        else:
                            error_msg = str(error_data["error"])
                except:
                    pass
                raise Exception(f"API Proxy Error ({response.status_code}): {error_msg}")

            # 解析响应
            result = response.json()

            # 创建响应对象
            return ChatCompletionResponse(result)

        except requests.exceptions.RequestException as e:
            raise Exception(f"网络错误: {str(e)}")
        except Exception as e:
            raise Exception(f"处理请求时出错: {str(e)}")


class ChatCompletionResponse:
    def __init__(self, data):
        self.id = data.get("id", "")
        self.choices = [Choice(choice) for choice in data.get("choices", [])]


class Choice:
    def __init__(self, data):
        self.message = Message(data.get("message", {}))
        self.index = data.get("index", 0)
        self.finish_reason = data.get("finish_reason", None)


class Message:
    def __init__(self, data):
        self.role = data.get("role", "assistant")
        self.content = data.get("content", "")


def initialize_client(api_key, proxy_url=None):
    """初始化客户端，如果提供了代理URL则使用代理"""
    if proxy_url:
        return CloudflareProxyClient(api_key, proxy_url)
    else:
        from openai import OpenAI
        return OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )


# 主应用
def main():
    st.title("🧬 DNA作业分析与批改")

    # 从Streamlit Secrets或环境变量获取默认代理URL
    default_proxy_url = st.secrets.get("api", {}).get("proxy_url", "") or os.environ.get("PROXY_URL", "")

    # 设置API密钥和代理URL
    with st.sidebar:
        st.header("API设置")
        api_key = st.text_input("阿里云百炼API Key", type="password", key="api_key")

        st.subheader("代理设置")
        use_proxy = st.checkbox("使用Cloudflare Worker代理", value=True, key="use_proxy")

        if use_proxy:
            proxy_url = st.text_input(
                "Cloudflare Worker URL",
                value=default_proxy_url,
                placeholder="https://your-worker.your-username.workers.dev",
                key="proxy_url"
            )
            st.info("Cloudflare Worker代理可以帮助解决跨境访问阿里云API的问题")
        else:
            proxy_url = None
            st.warning("直连阿里云API可能在国际网络环境下不可用")

    # 上传图片
    st.header("上传作业图片")
    uploaded_file = st.file_uploader("选择一个图片文件", type=["jpg", "jpeg", "png"])

    is_dna_image = st.checkbox("这是包含DNA结构的图片，需要专门分析", value=True)

    # 创建目录
    os.makedirs("temp_uploads", exist_ok=True)

    if uploaded_file and (api_key or (use_proxy and proxy_url)):
        # 显示上传的图片
        image = Image.open(uploaded_file)
        st.image(image, caption="上传的作业图片", use_column_width=True)

        # 分析按钮
        if st.button("分析作业"):
            with st.spinner("正在分析..."):
                try:
                    # 保存图片到临时文件
                    timestamp = int(time.time())
                    image_path = f"temp_uploads/image_{timestamp}.png"
                    image = resize_image(image, max_size=1024)
                    image = compress_image(image, quality=85)
                    image.save(image_path)

                    # 初始化API客户端 - 如果使用代理，传递代理URL
                    client = initialize_client(
                        api_key=api_key,
                        proxy_url=proxy_url if use_proxy else None
                    )

                    # 1. 提取文本
                    with st.spinner("正在识别图片文本..."):
                        image_base64 = image_to_base64(image)

                        response = client.chat.completions.create(
                            model="qwen-vl-plus",
                            messages=[
                                {"role": "system",
                                 "content": "你是一个优秀的图像文本识别助手。请从这张高中生物DNA相关作业的图片中识别并提取所有文字内容。"},
                                {"role": "user", "content": [
                                    {"type": "text",
                                     "text": "请仔细识别这张高中生物作业图片中的所有文字内容，包括DNA相关的专业术语、题目和答案。"},
                                    {"type": "image_url",
                                     "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                                ]}
                            ],
                            max_tokens=1500
                        )

                        extracted_text = response.choices[0].message.content

                    # 2. 如果是DNA图像，进行结构分析
                    dna_analysis = None
                    if is_dna_image:
                        with st.spinner("正在分析DNA结构..."):
                            response = client.chat.completions.create(
                                model="qwen-vl-plus",
                                messages=[
                                    {"role": "system",
                                     "content": "你是一位专业的生物学教师，精通DNA结构分析。请评估这张DNA相关图像中的内容是否正确，找出可能存在的错误。"},
                                    {"role": "user", "content": [
                                        {"type": "text",
                                         "text": "请分析这张DNA图像，检查以下几点：\n1. DNA结构是否正确表示\n2. 碱基配对是否正确（A-T, G-C）\n3. 螺旋结构是否准确\n4. 标注是否正确\n5. 图像中是否存在任何概念性错误\n\n请提供详细评估和改进建议。"},
                                        {"type": "image_url",
                                         "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                                    ]}
                                ],
                                max_tokens=1500
                            )

                            dna_analysis = response.choices[0].message.content

                    # 3. 综合评估
                    with st.spinner("正在评估作业内容..."):
                        system_prompt = "你是一位资深高中生物教师，专注于DNA和遗传学教学。请对学生的DNA作业和DNA图像进行综合评估和批改。"

                        user_prompt = f"""请综合评估以下高中生物DNA作业：

【学生提交的文字内容】
{extracted_text}
"""

                        if dna_analysis:
                            user_prompt += f"""
【DNA图像分析结果】
{dna_analysis}
"""

                        user_prompt += """
请按以下格式提供综合评估结果：
1. 作业正确性评估：评分1-100分
2. DNA图像分析：评论图像中的DNA结构是否正确，存在哪些问题
3. 文字内容评估：评论学生的文字回答
4. 错误分析与纠正：指出具体错误并提供正确解答
5. 相关生物知识点讲解：针对作业内容补充重要的DNA相关知识点
6. 学习建议：给出继续学习的方向和建议"""

                        response = client.chat.completions.create(
                            model="qwen-vl-plus",
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": [
                                    {"type": "text", "text": user_prompt},
                                    {"type": "image_url",
                                     "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                                ]}
                            ],
                            max_tokens=1800
                        )

                        feedback = response.choices[0].message.content

                    # 显示结果
                    st.success("分析完成！")

                    # 创建标签页显示不同结果
                    tabs = st.tabs(["作业评估", "识别文本", "DNA分析"])

                    with tabs[0]:
                        st.markdown(feedback)

                    with tabs[1]:
                        st.markdown("### 识别的文本内容")
                        st.write(extracted_text)

                    with tabs[2]:
                        if dna_analysis:
                            st.markdown("### DNA结构分析")
                            st.write(dna_analysis)
                        else:
                            st.info("未进行DNA结构专门分析")

                    # 记录分析结果
                    result_data = {
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "extracted_text": extracted_text,
                        "dna_analysis": dna_analysis,
                        "feedback": feedback,
                        "image_path": image_path
                    }

                    # 保存结果
                    os.makedirs("analysis_results", exist_ok=True)
                    with open(f"analysis_results/result_{timestamp}.json", "w", encoding="utf-8") as f:
                        json.dump(result_data, f, ensure_ascii=False, indent=2)

                except Exception as e:
                    st.error(f"分析过程中出错: {str(e)}")
                    st.markdown("**错误详情：**")
                    st.code(str(e))

                    if "API Proxy Error" in str(e):
                        st.markdown("""
                        **代理服务器错误**

                        Cloudflare Worker 代理可能遇到了以下问题：
                        1. Worker URL 不正确或无法访问
                        2. Worker 转发请求到阿里云时遇到问题
                        3. 阿里云API返回了错误

                        请检查：
                        - Cloudflare Worker URL 是否正确
                        - Worker 是否已正确部署
                        - API密钥是否有效
                        """)
                    elif "network" in str(e).lower():
                        st.markdown("""
                        **网络连接错误**

                        无法连接到代理服务器或阿里云API。请检查：
                        - 网络连接是否正常
                        - 代理URL是否正确
                        - 防火墙设置是否阻止了连接
                        """)
                    else:
                        st.markdown("""
                        **一般错误**

                        1. API密钥可能无效
                        2. 图片可能过大或格式不支持
                        3. 阿里云账户可能有配额限制

                        请尝试：
                        - 检查API密钥
                        - 压缩图片或使用不同格式
                        - 查看阿里云账户状态
                        """)

    elif not api_key and uploaded_file:
        st.warning("请在侧边栏输入阿里云百炼API密钥")
    elif not proxy_url and use_proxy and uploaded_file:
        st.warning("您选择了使用代理，但未提供代理URL。请填写Cloudflare Worker URL。")

    # 帮助信息
    with st.expander("使用说明"):
        st.markdown("""
        ### 使用步骤

        1. 在侧边栏设置阿里云百炼API密钥
        2. 启用Cloudflare Worker代理并设置代理URL（推荐）
        3. 上传包含DNA相关内容的作业图片
        4. 设置是否需要专门分析DNA结构
        5. 点击"分析作业"按钮
        6. 查看分析结果

        ### 注意事项

        - 图片建议不超过1MB，支持JPG、JPEG、PNG格式
        - 阿里云百炼API的max_tokens参数限制为最大2000
        - 分析过程可能需要30秒左右，请耐心等待
        """)

    # 底部信息
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 关于本应用")
    st.sidebar.markdown("""
    DNA作业批改助手 v1.0

    使用阿里云百炼API进行图像识别与分析
    使用Cloudflare Worker作为API代理
    """)

    # 增加对移动设备的支持
    st.markdown("""
    <style>
    .stApp {
        max-width: 100%;
    }
    @media (max-width: 768px) {
        .stImage > img {
            max-width: 100%;
            height: auto;
        }
    }
    </style>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()