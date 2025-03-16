import streamlit as st
from PIL import Image
import io
import base64
import os
import time
from openai import OpenAI

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


def initialize_client(api_key):
    return OpenAI(
        api_key="sk-60dbb95cc7404db7bcc28e04b8840f8e",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


# 主应用
def main():
    st.title("🧬 DNA作业分析与批改")

    # 设置API密钥
    api_key = st.sidebar.text_input("阿里云百炼API Key", type="password")
    use_proxy = st.sidebar.checkbox("使用代理", value=False)

    if use_proxy:
        proxy_host = st.sidebar.text_input("代理服务器地址", value="localhost")
        proxy_port = st.sidebar.text_input("代理服务器端口", value="7890")
        os.environ["http_proxy"] = f"http://{proxy_host}:{proxy_port}"
        os.environ["https_proxy"] = f"http://{proxy_host}:{proxy_port}"

    # 上传图片
    st.header("上传作业图片")
    uploaded_file = st.file_uploader("选择一个图片文件", type=["jpg", "jpeg", "png"])

    is_dna_image = st.checkbox("这是包含DNA结构的图片，需要专门分析", value=True)

    # 创建目录
    os.makedirs("temp_uploads", exist_ok=True)

    if uploaded_file and api_key:
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

                    # 初始化API客户端
                    client = initialize_client(api_key)

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
                            max_tokens=1500,  # 修改为低于2000的值
                            stream=False
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
                                max_tokens=1500,  # 修改为低于2000的值
                                stream=False
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

                        # 分步执行评估以减少单次返回的内容量
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
                            max_tokens=2000,  # 修改为不超过2000的值
                            stream=False
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

                except Exception as e:
                    st.error(f"分析过程中出错: {str(e)}")
                    st.markdown("**错误详情：**")
                    st.code(str(e))
                    st.markdown("**可能原因与解决方法:**")
                    st.markdown("1. API密钥无效或不正确 - 检查API密钥格式")
                    st.markdown("2. 网络连接问题 - 尝试设置代理")
                    st.markdown("3. 图片过大或格式问题 - 尝试压缩图片或转换格式")
                    st.markdown("4. 阿里云API限制 - 检查账户余额和配额")

    elif not api_key and uploaded_file:
        st.warning("请在侧边栏输入阿里云百炼API密钥")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 帮助信息")
    st.sidebar.markdown("""
    1. 上传包含DNA相关内容的作业图片
    2. 设置是否需要专门分析DNA结构
    3. 点击"分析作业"按钮
    4. 系统将自动识别文本、分析结构并评估作业

    **注意事项：**
    - 阿里云百炼API的max_tokens参数限制为最大2000
    - 图片大小建议不超过1MB
    - 支持JPG、JPEG、PNG格式
    """)


if __name__ == "__main__":
    main()