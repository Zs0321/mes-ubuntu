"""
AI报价系统 - 数据分析模块
用于历史报价数据的分析和异常检测
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


@dataclass
class AnalysisResult:
    """分析结果数据类"""
    summary: Dict
    anomalies: pd.DataFrame
    recommendations: List[str]


class QuotationDataAnalyzer:
    """报价数据分析器"""
    
    # 产品类型映射
    PRODUCT_TYPES = {
        '电机': 'motor',
        '控制器': 'controller',
        'PDU': 'pdu',
        'DCDC': 'dcdc',
        'OBC': 'obc'
    }
    
    # 材料类别
    MATERIAL_CATEGORIES = {
        '铝制品': ['铝压铸', '铝机加工', '铝拉伸'],
        '机械部件': ['轴', '轴承'],
        '电磁材料': ['硅钢片', '磁钢', '铜线'],
        '传感器': ['旋转变压器'],
        '电子元器件': ['PCBA', 'IGBT', 'MOS', '连接器', '线束'],
        '结构件': ['塑料壳体']
    }
    
    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.scaler = StandardScaler()
        
    def load_data(self, file_path: str) -> pd.DataFrame:
        """
        加载报价数据
        
        Args:
            file_path: Excel或CSV文件路径
            
        Returns:
            加载的DataFrame
        """
        if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
            self.df = pd.read_excel(file_path)
        elif file_path.endswith('.csv'):
            self.df = pd.read_csv(file_path)
        else:
            raise ValueError("不支持的文件格式，请使用Excel或CSV")
        
        print(f"成功加载 {len(self.df)} 条报价记录")
        return self.df
    
    def clean_data(self) -> pd.DataFrame:
        """
        数据清洗
        
        Returns:
            清洗后的DataFrame
        """
        if self.df is None:
            raise ValueError("请先加载数据")
        
        original_count = len(self.df)
        
        # 1. 删除关键字段缺失的记录
        key_columns = ['unit_price', 'power_kw']
        existing_key_cols = [col for col in key_columns if col in self.df.columns]
        if existing_key_cols:
            self.df = self.df.dropna(subset=existing_key_cols)
        
        # 2. 删除负值和零值
        if 'unit_price' in self.df.columns:
            self.df = self.df[self.df['unit_price'] > 0]
        
        # 3. 标准化产品类型
        if 'product_type' in self.df.columns:
            self.df['product_type'] = self.df['product_type'].str.strip()
        
        # 4. 日期格式化
        if 'quotation_date' in self.df.columns:
            self.df['quotation_date'] = pd.to_datetime(
                self.df['quotation_date'], 
                errors='coerce'
            )
        
        cleaned_count = len(self.df)
        print(f"数据清洗完成: {original_count} -> {cleaned_count} 条记录")
        print(f"删除了 {original_count - cleaned_count} 条无效记录")
        
        return self.df
    
    def analyze_price_distribution(
        self, 
        group_by: str = 'product_type'
    ) -> Dict:
        """
        分析价格分布
        
        Args:
            group_by: 分组字段
            
        Returns:
            各组的价格统计信息
        """
        if self.df is None:
            raise ValueError("请先加载数据")
        
        results = {}
        
        if group_by in self.df.columns:
            for group_name, group_df in self.df.groupby(group_by):
                results[group_name] = {
                    'count': len(group_df),
                    'mean': group_df['unit_price'].mean(),
                    'std': group_df['unit_price'].std(),
                    'median': group_df['unit_price'].median(),
                    'min': group_df['unit_price'].min(),
                    'max': group_df['unit_price'].max(),
                    'q25': group_df['unit_price'].quantile(0.25),
                    'q75': group_df['unit_price'].quantile(0.75)
                }
        else:
            # 整体统计
            results['overall'] = {
                'count': len(self.df),
                'mean': self.df['unit_price'].mean(),
                'std': self.df['unit_price'].std(),
                'median': self.df['unit_price'].median(),
                'min': self.df['unit_price'].min(),
                'max': self.df['unit_price'].max(),
                'q25': self.df['unit_price'].quantile(0.25),
                'q75': self.df['unit_price'].quantile(0.75)
            }
        
        return results
    
    def analyze_cost_ratio(self) -> Dict:
        """
        分析成本占比
        
        Returns:
            成本占比统计
        """
        if self.df is None:
            raise ValueError("请先加载数据")
        
        if 'bom_cost' not in self.df.columns or 'unit_price' not in self.df.columns:
            return {'error': '缺少bom_cost或unit_price字段'}
        
        # 计算成本率
        self.df['cost_ratio'] = self.df['bom_cost'] / self.df['unit_price']
        self.df['margin_rate'] = 1 - self.df['cost_ratio']
        
        results = {
            'overall': {
                'avg_cost_ratio': self.df['cost_ratio'].mean(),
                'avg_margin_rate': self.df['margin_rate'].mean(),
                'min_margin': self.df['margin_rate'].min(),
                'max_margin': self.df['margin_rate'].max()
            }
        }
        
        # 按产品类型分组
        if 'product_type' in self.df.columns:
            results['by_product'] = {}
            for ptype, group in self.df.groupby('product_type'):
                results['by_product'][ptype] = {
                    'avg_cost_ratio': group['cost_ratio'].mean(),
                    'avg_margin_rate': group['margin_rate'].mean(),
                    'count': len(group)
                }
        
        return results
    
    def detect_anomalies_iqr(
        self, 
        column: str = 'unit_price',
        multiplier: float = 1.5
    ) -> pd.DataFrame:
        """
        使用IQR方法检测异常
        
        Args:
            column: 检测的列
            multiplier: IQR倍数
            
        Returns:
            异常记录DataFrame
        """
        if self.df is None:
            raise ValueError("请先加载数据")
        
        Q1 = self.df[column].quantile(0.25)
        Q3 = self.df[column].quantile(0.75)
        IQR = Q3 - Q1
        
        lower_bound = Q1 - multiplier * IQR
        upper_bound = Q3 + multiplier * IQR
        
        anomalies = self.df[
            (self.df[column] < lower_bound) | 
            (self.df[column] > upper_bound)
        ].copy()
        
        anomalies['anomaly_type'] = anomalies[column].apply(
            lambda x: '过低' if x < lower_bound else '过高'
        )
        anomalies['deviation'] = anomalies[column].apply(
            lambda x: (x - lower_bound) if x < lower_bound else (x - upper_bound)
        )
        
        print(f"检测到 {len(anomalies)} 条异常报价")
        return anomalies
    
    def detect_anomalies_ml(
        self, 
        features: List[str] = None,
        contamination: float = 0.1
    ) -> pd.DataFrame:
        """
        使用机器学习方法检测异常
        
        Args:
            features: 用于检测的特征列
            contamination: 预期异常比例
            
        Returns:
            异常记录DataFrame
        """
        if self.df is None:
            raise ValueError("请先加载数据")
        
        if features is None:
            features = ['unit_price', 'power_kw', 'quantity']
        
        # 过滤存在的特征
        available_features = [f for f in features if f in self.df.columns]
        if not available_features:
            raise ValueError("没有可用的特征列")
        
        # 准备数据
        X = self.df[available_features].dropna()
        X_scaled = self.scaler.fit_transform(X)
        
        # Isolation Forest
        clf = IsolationForest(
            contamination=contamination,
            random_state=42
        )
        predictions = clf.fit_predict(X_scaled)
        
        # 标记异常
        anomaly_mask = predictions == -1
        anomalies = self.df.loc[X.index[anomaly_mask]].copy()
        anomalies['anomaly_score'] = clf.decision_function(X_scaled)[anomaly_mask]
        
        print(f"ML方法检测到 {len(anomalies)} 条异常报价")
        return anomalies
    
    def analyze_power_price_relationship(self) -> Dict:
        """
        分析功率与价格的关系
        
        Returns:
            相关性分析结果
        """
        if self.df is None:
            raise ValueError("请先加载数据")
        
        if 'power_kw' not in self.df.columns or 'unit_price' not in self.df.columns:
            return {'error': '缺少power_kw或unit_price字段'}
        
        # 计算相关系数
        correlation = self.df['power_kw'].corr(self.df['unit_price'])
        
        # 计算每KW单价
        self.df['price_per_kw'] = self.df['unit_price'] / self.df['power_kw']
        
        results = {
            'correlation': correlation,
            'avg_price_per_kw': self.df['price_per_kw'].mean(),
            'std_price_per_kw': self.df['price_per_kw'].std()
        }
        
        # 按功率区间统计
        power_bins = [0, 10, 50, 100, 200, 500, float('inf')]
        power_labels = ['0-10KW', '10-50KW', '50-100KW', '100-200KW', '200-500KW', '>500KW']
        
        self.df['power_range'] = pd.cut(
            self.df['power_kw'], 
            bins=power_bins, 
            labels=power_labels
        )
        
        results['by_power_range'] = {}
        for prange, group in self.df.groupby('power_range'):
            if len(group) > 0:
                results['by_power_range'][prange] = {
                    'count': len(group),
                    'avg_price': group['unit_price'].mean(),
                    'avg_price_per_kw': group['price_per_kw'].mean()
                }
        
        return results
    
    def generate_analysis_report(self) -> AnalysisResult:
        """
        生成完整的分析报告
        
        Returns:
            分析结果对象
        """
        summary = {}
        recommendations = []
        
        # 1. 价格分布分析
        price_dist = self.analyze_price_distribution()
        summary['price_distribution'] = price_dist
        
        # 2. 成本占比分析
        cost_ratio = self.analyze_cost_ratio()
        summary['cost_analysis'] = cost_ratio
        
        # 3. 功率价格关系
        power_price = self.analyze_power_price_relationship()
        summary['power_price_analysis'] = power_price
        
        # 4. 异常检测
        anomalies_iqr = self.detect_anomalies_iqr()
        anomalies_ml = self.detect_anomalies_ml()
        
        # 合并异常（去重）
        all_anomalies = pd.concat([anomalies_iqr, anomalies_ml]).drop_duplicates()
        
        # 5. 生成建议
        if 'cost_analysis' in summary and 'overall' in summary['cost_analysis']:
            avg_margin = summary['cost_analysis']['overall'].get('avg_margin_rate', 0)
            if avg_margin < 0.2:
                recommendations.append("⚠️ 平均毛利率偏低(<20%)，建议审查定价策略")
            elif avg_margin > 0.5:
                recommendations.append("⚠️ 部分产品毛利率过高(>50%)，可能影响竞争力")
        
        if len(all_anomalies) > 0:
            recommendations.append(f"🔍 发现 {len(all_anomalies)} 条异常报价，建议逐一审核")
        
        if 'power_price_analysis' in summary:
            corr = summary['power_price_analysis'].get('correlation', 0)
            if corr < 0.5:
                recommendations.append("📊 功率与价格相关性较低，定价可能缺乏一致性")
        
        return AnalysisResult(
            summary=summary,
            anomalies=all_anomalies,
            recommendations=recommendations
        )


def main():
    """示例用法"""
    analyzer = QuotationDataAnalyzer()
    
    # 模拟数据（实际使用时替换为真实文件路径）
    print("=" * 50)
    print("AI报价系统 - 数据分析模块")
    print("=" * 50)
    print("\n请使用以下方式加载数据:")
    print("  analyzer.load_data('your_quotation_file.xlsx')")
    print("  analyzer.clean_data()")
    print("  report = analyzer.generate_analysis_report()")


if __name__ == "__main__":
    main()
