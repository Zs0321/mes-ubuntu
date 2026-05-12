"""Claude Vision API 实现"""
import anthropic
import base64
import time
from typing import List, Dict, Any
from .vision_api import VisionAPIInterface, VisionAnalysisResult
from .token_usage_logger import log_ai_token_usage

class ClaudeVisionAPI(VisionAPIInterface):
    def __init__(self, config: Dict[str, Any]):
        self.client = anthropic.Anthropic(api_key=config["api_key"])
        self.model = config.get("model", "claude-sonnet-4-5-20250929")

    def analyze_process_photos(
        self,
        process_name: str,
        photos: List[bytes],
        reference_images: List[bytes],
        rules: Dict[str, Any]
    ) -> VisionAnalysisResult:
        """调用 Claude Vision API 分析照片"""

        # 构建 prompt
        prompt = self._build_prompt(process_name, rules)

        # 构建消息内容
        content = []

        # 添加参考图片
        for ref_img in reference_images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(ref_img).decode()
                }
            })

        # 添加待检测照片
        for photo in photos:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(photo).decode()
                }
            })

        # 添加文本 prompt
        content.append({"type": "text", "text": prompt})

        # 调用 API
        start_ts = time.time()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": content}]
        )
        latency_ms = int((time.time() - start_ts) * 1000)
        usage = getattr(response, "usage", None)
        usage_dict = {
            "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
            "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
        }
        log_ai_token_usage(
            provider="claude",
            model=self.model,
            usage=usage_dict,
            image_path="",
            latency_ms=latency_ms,
            success=True,
            error_message="",
        )

        # 解析响应
        return self._parse_response(response)

    def _build_prompt(self, process_name: str, rules: Dict[str, Any]) -> str:
        """构建中文 prompt"""
        check_items = rules.get("check_items", [])
        pass_criteria = rules.get("pass_criteria", "")

        prompt = f"""你是一个电机质检专家。请分析以下工序的照片：

工序名称：{process_name}

检查项目：
{chr(10).join(f"- {item}" for item in check_items)}

合格标准：{pass_criteria}

请返回分析结果（JSON格式）：
{{
    "status": "pass/fail/ng",
    "confidence": 0.0-1.0,
    "issues": ["问题1", "问题2"],
    "summary": "分析总结"
}}

说明：
- pass: 合格
- fail: 不合格，需要返工
- ng: 需要人工复核
- confidence: 判断的置信度
- issues: 发现的具体问题列表（如果合格则为空）
- summary: 简要总结分析结果
"""
        return prompt

    def _parse_response(self, response) -> VisionAnalysisResult:
        """解析 Claude API 响应"""
        import json

        text = response.content[0].text

        # 尝试解析 JSON
        try:
            # 提取 JSON 部分
            start = text.find('{')
            end = text.rfind('}') + 1
            json_str = text[start:end]
            result = json.loads(json_str)

            return VisionAnalysisResult(
                status=result.get("status", "ng"),
                confidence=float(result.get("confidence", 0.0)),
                issues=result.get("issues", []),
                summary=result.get("summary", ""),
                raw_response={"text": text, "parsed": result}
            )
        except (json.JSONDecodeError, ValueError) as e:
            # 解析失败，返回 ng 状态
            return VisionAnalysisResult(
                status="ng",
                confidence=0.0,
                issues=["API 响应解析失败"],
                summary=f"解析错误: {str(e)}",
                raw_response={"text": text, "error": str(e)}
            )

    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """简化的单图片分析接口

        Args:
            image_path: 图片路径
            prompt: 分析提示词

        Returns:
            Dict with keys: analysis (str), defects (list)
        """
        # 读取图片
        with open(image_path, 'rb') as f:
            image_data = f.read()

        # 构建消息内容
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(image_data).decode()
                }
            },
            {
                "type": "text",
                "text": prompt + "\n\n请返回JSON格式：{\"analysis\": \"分析结果\", \"defects\": [\"缺陷列表\"]}"
            }
        ]

        # 调用 API
        start_ts = time.time()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            messages=[{"role": "user", "content": content}]
        )
        latency_ms = int((time.time() - start_ts) * 1000)
        usage = getattr(response, "usage", None)
        usage_dict = {
            "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
            "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
        }
        log_ai_token_usage(
            provider="claude",
            model=self.model,
            usage=usage_dict,
            image_path=image_path,
            latency_ms=latency_ms,
            success=True,
            error_message="",
        )

        # 解析响应
        import json
        text = response.content[0].text

        try:
            # 提取 JSON 部分
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                result = json.loads(json_str)
                return {
                    "analysis": result.get("analysis", text),
                    "defects": result.get("defects", [])
                }
        except (json.JSONDecodeError, ValueError):
            pass

        # 如果解析失败，返回原始文本
        return {
            "analysis": text,
            "defects": []
        }
