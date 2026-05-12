"""
AI报价系统 - AI助手模块
集成LLM进行智能分析和问答
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass
import json


@dataclass
class AIAnalysisResult:
    """AI分析结果"""
    recommendation: str
    price_range: tuple
    analysis: str
    risks: List[str]
    suggestions: List[str]


class QuotationAIAssistant:
    """
    报价AI助手
    支持多种LLM后端: OpenAI GPT, 通义千问, 文心一言等
    """
    
    # 报价分析Prompt模板
    QUOTATION_ANALYSIS_PROMPT = """
你是一位专业的电机和电机控制器报价分析专家，精通工程机械电动化领域的产品定价。

## 产品信息
- 产品类型: {product_type}
- 功率: {power_kw} KW
- 电压: {voltage_v} V
- 数量: {quantity} 台
- BOM成本: ¥{bom_cost}
- 客户类型: {customer}

## 原材料构成
{materials}

## 相似历史案例
{similar_cases}

## 请提供以下分析

### 1. 推荐报价
基于成本和历史数据，给出推荐的单价区间。

### 2. 定价依据
详细说明定价的主要考虑因素。

### 3. 风险评估
指出定价可能存在的风险点。

### 4. 优化建议
提供成本优化或报价策略的建议。

请以JSON格式返回结果:
{{
    "recommended_price": 数字,
    "price_range": [最低, 最高],
    "pricing_basis": "定价依据说明",
    "risks": ["风险1", "风险2"],
    "suggestions": ["建议1", "建议2"]
}}
"""

    ANOMALY_EXPLANATION_PROMPT = """
以下报价被系统标记为异常，请分析可能的原因：

## 报价信息
{quotation_info}

## 异常类型
{anomaly_type}

## 异常详情
{anomaly_details}

请分析:
1. 可能的业务合理性解释（如特殊客户、批量优惠、市场竞争等）
2. 如果确实是定价错误，可能的原因
3. 建议的处理方式

请给出专业、客观的分析。
"""

    QA_PROMPT = """
你是一位专业的电机和电机控制器报价顾问。

用户的问题: {question}

相关背景知识:
{context}

请基于你的专业知识和提供的背景信息，给出准确、有帮助的回答。
"""

    def __init__(
        self, 
        provider: str = "openai",
        api_key: str = None,
        model: str = None
    ):
        """
        初始化AI助手
        
        Args:
            provider: LLM提供商 ('openai', 'qwen', 'wenxin')
            api_key: API密钥
            model: 模型名称
        """
        self.provider = provider
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.model = model or self._get_default_model(provider)
        self.client = None
        
        self._init_client()
    
    def _get_default_model(self, provider: str) -> str:
        """获取默认模型"""
        defaults = {
            "openai": "gpt-4",
            "qwen": "qwen-plus",
            "wenxin": "ernie-bot-4"
        }
        return defaults.get(provider, "gpt-3.5-turbo")
    
    def _init_client(self):
        """初始化LLM客户端"""
        if not self.api_key:
            print("警告: 未设置API密钥，AI功能将使用模拟模式")
            return
        
        try:
            if self.provider == "openai":
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            elif self.provider == "qwen":
                # 通义千问
                import dashscope
                dashscope.api_key = self.api_key
                self.client = dashscope
            # 其他提供商可以按需添加
        except ImportError as e:
            print(f"警告: 缺少必要的库 - {e}")
            self.client = None
    
    def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        if not self.client:
            return self._mock_response(prompt)
        
        try:
            if self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一位专业的电机报价分析专家。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3
                )
                return response.choices[0].message.content
            
            elif self.provider == "qwen":
                from dashscope import Generation
                response = Generation.call(
                    model=self.model,
                    prompt=prompt
                )
                return response.output.text
            
        except Exception as e:
            print(f"LLM调用失败: {e}")
            return self._mock_response(prompt)
    
    def _mock_response(self, prompt: str) -> str:
        """模拟响应（用于测试或API不可用时）"""
        return json.dumps({
            "recommended_price": 12500,
            "price_range": [11800, 13200],
            "pricing_basis": "基于BOM成本和25%目标毛利率计算",
            "risks": [
                "原材料价格波动风险",
                "批量定价可能影响利润"
            ],
            "suggestions": [
                "建议锁定主要材料价格",
                "可考虑分期交付以控制风险"
            ]
        }, ensure_ascii=False, indent=2)
    
    def analyze_quotation(
        self,
        product_info: Dict,
        similar_cases: List[Dict] = None
    ) -> AIAnalysisResult:
        """
        分析报价并给出建议
        
        Args:
            product_info: 产品信息字典
            similar_cases: 相似历史案例列表
            
        Returns:
            AI分析结果
        """
        # 格式化材料信息
        materials_str = "无材料明细"
        if 'materials' in product_info:
            materials_str = "\n".join([
                f"- {m['name']}: {m.get('quantity', 'N/A')} {m.get('unit', '')}"
                for m in product_info['materials']
            ])
        
        # 格式化相似案例
        cases_str = "暂无相似案例"
        if similar_cases:
            cases_str = "\n".join([
                f"案例{i+1}: {c['product']} - ¥{c['price']}/台 (成交:{c.get('status', 'N/A')})"
                for i, c in enumerate(similar_cases[:5])
            ])
        
        # 构建Prompt
        prompt = self.QUOTATION_ANALYSIS_PROMPT.format(
            product_type=product_info.get('product_type', '未知'),
            power_kw=product_info.get('power_kw', 'N/A'),
            voltage_v=product_info.get('voltage_v', 'N/A'),
            quantity=product_info.get('quantity', 1),
            bom_cost=product_info.get('bom_cost', 'N/A'),
            customer=product_info.get('customer', '普通客户'),
            materials=materials_str,
            similar_cases=cases_str
        )
        
        # 调用LLM
        response = self._call_llm(prompt)
        
        # 解析响应
        try:
            result = json.loads(response)
            return AIAnalysisResult(
                recommendation=f"推荐报价: ¥{result['recommended_price']}",
                price_range=tuple(result['price_range']),
                analysis=result['pricing_basis'],
                risks=result['risks'],
                suggestions=result['suggestions']
            )
        except json.JSONDecodeError:
            return AIAnalysisResult(
                recommendation="解析失败，请查看原始响应",
                price_range=(0, 0),
                analysis=response,
                risks=[],
                suggestions=[]
            )
    
    def explain_anomaly(
        self,
        quotation: Dict,
        anomaly_type: str,
        anomaly_details: str
    ) -> str:
        """
        解释异常报价
        
        Args:
            quotation: 报价信息
            anomaly_type: 异常类型
            anomaly_details: 异常详情
            
        Returns:
            解释文本
        """
        prompt = self.ANOMALY_EXPLANATION_PROMPT.format(
            quotation_info=json.dumps(quotation, ensure_ascii=False, indent=2),
            anomaly_type=anomaly_type,
            anomaly_details=anomaly_details
        )
        
        return self._call_llm(prompt)
    
    def answer_question(
        self,
        question: str,
        context: str = ""
    ) -> str:
        """
        回答定价相关问题
        
        Args:
            question: 用户问题
            context: 相关背景信息
            
        Returns:
            回答文本
        """
        prompt = self.QA_PROMPT.format(
            question=question,
            context=context or "暂无额外背景信息"
        )
        
        return self._call_llm(prompt)
    
    def generate_quotation_report(
        self,
        quotation: Dict,
        analysis_result: AIAnalysisResult
    ) -> str:
        """
        生成报价报告
        
        Args:
            quotation: 报价信息
            analysis_result: 分析结果
            
        Returns:
            报告文本(Markdown格式)
        """
        report = f"""
# 报价分析报告

## 1. 产品信息

| 项目 | 内容 |
|------|------|
| 产品类型 | {quotation.get('product_type', 'N/A')} |
| 功率 | {quotation.get('power_kw', 'N/A')} KW |
| 电压 | {quotation.get('voltage_v', 'N/A')} V |
| 数量 | {quotation.get('quantity', 'N/A')} 台 |
| BOM成本 | ¥{quotation.get('bom_cost', 'N/A')} |

## 2. AI推荐

**{analysis_result.recommendation}**

推荐价格区间: ¥{analysis_result.price_range[0]} - ¥{analysis_result.price_range[1]}

## 3. 定价依据

{analysis_result.analysis}

## 4. 风险提示

"""
        for risk in analysis_result.risks:
            report += f"- ⚠️ {risk}\n"
        
        report += "\n## 5. 优化建议\n\n"
        for suggestion in analysis_result.suggestions:
            report += f"- 💡 {suggestion}\n"
        
        return report


def main():
    """示例用法"""
    print("=" * 50)
    print("AI报价系统 - AI助手模块")
    print("=" * 50)
    
    # 初始化（使用模拟模式）
    assistant = QuotationAIAssistant()
    
    # 测试分析
    product_info = {
        'product_type': '永磁同步电机',
        'power_kw': 100,
        'voltage_v': 400,
        'quantity': 50,
        'bom_cost': 8500,
        'customer': '重点客户A',
        'materials': [
            {'name': '铝压铸壳体', 'quantity': 1, 'unit': '件'},
            {'name': '硅钢片', 'quantity': 50, 'unit': 'kg'},
            {'name': '磁钢', 'quantity': 5, 'unit': 'kg'},
            {'name': '铜线', 'quantity': 20, 'unit': 'kg'}
        ]
    }
    
    similar_cases = [
        {'product': '100KW电机', 'price': 12300, 'status': '已成交'},
        {'product': '90KW电机', 'price': 11500, 'status': '已成交'},
    ]
    
    result = assistant.analyze_quotation(product_info, similar_cases)
    
    print("\nAI分析结果:")
    print(f"  推荐: {result.recommendation}")
    print(f"  价格区间: ¥{result.price_range[0]} - ¥{result.price_range[1]}")
    print(f"  风险数: {len(result.risks)}")
    print(f"  建议数: {len(result.suggestions)}")


if __name__ == "__main__":
    main()
