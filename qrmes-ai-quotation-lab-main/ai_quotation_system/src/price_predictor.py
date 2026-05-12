"""
AI报价系统 - 价格预测模块
基于机器学习的价格预测模型
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import joblib
from pathlib import Path

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
import xgboost as xgb


@dataclass
class PredictionResult:
    """预测结果数据类"""
    predicted_price: float
    price_range: Tuple[float, float]
    confidence: float
    feature_importance: Dict[str, float]


class PricePredictor:
    """价格预测器"""
    
    # 默认特征列表
    DEFAULT_FEATURES = [
        'power_kw',      # 功率
        'voltage_v',     # 电压
        'quantity',      # 数量
        'bom_cost',      # BOM成本
    ]
    
    # 分类特征
    CATEGORICAL_FEATURES = [
        'product_type',    # 产品类型
        'customer_level',  # 客户等级
        'cooling_type',    # 冷却方式
    ]
    
    def __init__(self, model_type: str = 'xgboost'):
        """
        初始化预测器
        
        Args:
            model_type: 模型类型 ('xgboost', 'random_forest', 'gradient_boosting')
        """
        self.model_type = model_type
        self.model = self._create_model(model_type)
        self.scaler = StandardScaler()
        self.label_encoders: Dict[str, LabelEncoder] = {}
        self.feature_names: List[str] = []
        self.is_trained = False
        
    def _create_model(self, model_type: str):
        """创建模型实例"""
        if model_type == 'xgboost':
            return xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1
            )
        elif model_type == 'random_forest':
            return RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                random_state=42,
                n_jobs=-1
            )
        elif model_type == 'gradient_boosting':
            return GradientBoostingRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42
            )
        else:
            raise ValueError(f"不支持的模型类型: {model_type}")
    
    def prepare_features(
        self, 
        df: pd.DataFrame, 
        is_training: bool = True
    ) -> pd.DataFrame:
        """
        特征工程
        
        Args:
            df: 输入数据
            is_training: 是否为训练模式
            
        Returns:
            处理后的特征DataFrame
        """
        features = pd.DataFrame()
        
        # 1. 数值特征
        for col in self.DEFAULT_FEATURES:
            if col in df.columns:
                features[col] = df[col].fillna(df[col].median())
        
        # 2. 分类特征编码
        for col in self.CATEGORICAL_FEATURES:
            if col in df.columns:
                if is_training:
                    self.label_encoders[col] = LabelEncoder()
                    features[col] = self.label_encoders[col].fit_transform(
                        df[col].fillna('unknown').astype(str)
                    )
                else:
                    if col in self.label_encoders:
                        # 处理未见过的类别
                        known_classes = set(self.label_encoders[col].classes_)
                        col_data = df[col].fillna('unknown').astype(str)
                        col_data = col_data.apply(
                            lambda x: x if x in known_classes else 'unknown'
                        )
                        features[col] = self.label_encoders[col].transform(col_data)
        
        # 3. 派生特征
        if 'power_kw' in df.columns and 'bom_cost' in df.columns:
            features['cost_per_kw'] = df['bom_cost'] / df['power_kw'].replace(0, 1)
        
        if 'power_kw' in df.columns and 'voltage_v' in df.columns:
            features['power_voltage_ratio'] = df['power_kw'] / df['voltage_v'].replace(0, 1)
        
        if 'quantity' in df.columns:
            features['log_quantity'] = np.log1p(df['quantity'])
        
        self.feature_names = list(features.columns)
        return features
    
    def train(
        self, 
        df: pd.DataFrame, 
        target_col: str = 'unit_price',
        test_size: float = 0.2
    ) -> Dict:
        """
        训练模型
        
        Args:
            df: 训练数据
            target_col: 目标列名
            test_size: 测试集比例
            
        Returns:
            训练评估指标
        """
        # 准备特征
        X = self.prepare_features(df, is_training=True)
        y = df[target_col]
        
        # 划分数据集
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )
        
        # 标准化
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # 训练
        self.model.fit(X_train_scaled, y_train)
        self.is_trained = True
        
        # 评估
        y_train_pred = self.model.predict(X_train_scaled)
        y_test_pred = self.model.predict(X_test_scaled)
        
        metrics = {
            'train': {
                'mae': mean_absolute_error(y_train, y_train_pred),
                'rmse': np.sqrt(mean_squared_error(y_train, y_train_pred)),
                'r2': r2_score(y_train, y_train_pred)
            },
            'test': {
                'mae': mean_absolute_error(y_test, y_test_pred),
                'rmse': np.sqrt(mean_squared_error(y_test, y_test_pred)),
                'r2': r2_score(y_test, y_test_pred)
            }
        }
        
        # 交叉验证
        cv_scores = cross_val_score(
            self.model, 
            self.scaler.transform(X), 
            y, 
            cv=5, 
            scoring='r2'
        )
        metrics['cv_r2_mean'] = cv_scores.mean()
        metrics['cv_r2_std'] = cv_scores.std()
        
        print(f"模型训练完成:")
        print(f"  训练集 R²: {metrics['train']['r2']:.4f}")
        print(f"  测试集 R²: {metrics['test']['r2']:.4f}")
        print(f"  交叉验证 R²: {metrics['cv_r2_mean']:.4f} ± {metrics['cv_r2_std']:.4f}")
        
        return metrics
    
    def predict(
        self, 
        features: Dict | pd.DataFrame,
        return_interval: bool = True,
        confidence_level: float = 0.9
    ) -> PredictionResult:
        """
        预测价格
        
        Args:
            features: 特征字典或DataFrame
            return_interval: 是否返回预测区间
            confidence_level: 置信水平
            
        Returns:
            预测结果
        """
        if not self.is_trained:
            raise ValueError("模型尚未训练")
        
        # 转换为DataFrame
        if isinstance(features, dict):
            features = pd.DataFrame([features])
        
        # 准备特征
        X = self.prepare_features(features, is_training=False)
        X_scaled = self.scaler.transform(X)
        
        # 预测
        predicted_price = self.model.predict(X_scaled)[0]
        
        # 计算预测区间（基于训练误差估计）
        if return_interval:
            # 简化的置信区间估计
            std_estimate = predicted_price * 0.1  # 假设10%的标准差
            z_score = 1.645 if confidence_level == 0.9 else 1.96  # 90%或95%
            margin = z_score * std_estimate
            price_range = (
                max(0, predicted_price - margin),
                predicted_price + margin
            )
        else:
            price_range = (predicted_price, predicted_price)
        
        # 特征重要性
        if hasattr(self.model, 'feature_importances_'):
            importance = dict(zip(
                self.feature_names,
                self.model.feature_importances_
            ))
        else:
            importance = {}
        
        return PredictionResult(
            predicted_price=predicted_price,
            price_range=price_range,
            confidence=confidence_level,
            feature_importance=importance
        )
    
    def get_feature_importance(self) -> Dict[str, float]:
        """获取特征重要性"""
        if not self.is_trained:
            raise ValueError("模型尚未训练")
        
        if hasattr(self.model, 'feature_importances_'):
            importance = dict(zip(
                self.feature_names,
                self.model.feature_importances_
            ))
            # 排序
            return dict(sorted(
                importance.items(), 
                key=lambda x: x[1], 
                reverse=True
            ))
        return {}
    
    def save_model(self, path: str):
        """保存模型"""
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'label_encoders': self.label_encoders,
            'feature_names': self.feature_names,
            'model_type': self.model_type
        }
        joblib.dump(model_data, path)
        print(f"模型已保存至: {path}")
    
    def load_model(self, path: str):
        """加载模型"""
        model_data = joblib.load(path)
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.label_encoders = model_data['label_encoders']
        self.feature_names = model_data['feature_names']
        self.model_type = model_data['model_type']
        self.is_trained = True
        print(f"模型已从 {path} 加载")


class QuotationCalculator:
    """报价计算器 - 基于规则的报价"""
    
    # 默认毛利率配置
    DEFAULT_MARGINS = {
        '电机': 0.25,
        '控制器': 0.28,
        'PDU': 0.22,
        'DCDC': 0.23,
        'OBC': 0.25
    }
    
    # 批量折扣
    VOLUME_DISCOUNTS = {
        (1, 10): 1.0,
        (10, 50): 0.95,
        (50, 100): 0.90,
        (100, 500): 0.85,
        (500, float('inf')): 0.80
    }
    
    # 客户等级折扣
    CUSTOMER_DISCOUNTS = {
        'A': 0.95,
        'B': 0.98,
        'C': 1.0,
        'D': 1.02
    }
    
    def __init__(self, custom_margins: Dict = None):
        """
        初始化计算器
        
        Args:
            custom_margins: 自定义毛利率配置
        """
        self.margins = custom_margins or self.DEFAULT_MARGINS
    
    def calculate_base_price(
        self,
        bom_cost: float,
        product_type: str,
        margin_rate: float = None
    ) -> float:
        """
        计算基础价格
        
        Args:
            bom_cost: BOM成本
            product_type: 产品类型
            margin_rate: 自定义毛利率
            
        Returns:
            基础价格
        """
        if margin_rate is None:
            margin_rate = self.margins.get(product_type, 0.25)
        
        return bom_cost / (1 - margin_rate)
    
    def get_volume_discount(self, quantity: int) -> float:
        """获取批量折扣"""
        for (low, high), discount in self.VOLUME_DISCOUNTS.items():
            if low <= quantity < high:
                return discount
        return 1.0
    
    def get_customer_discount(self, customer_level: str) -> float:
        """获取客户折扣"""
        return self.CUSTOMER_DISCOUNTS.get(customer_level.upper(), 1.0)
    
    def calculate_quotation(
        self,
        bom_cost: float,
        product_type: str,
        quantity: int = 1,
        customer_level: str = 'C',
        rd_allocation: float = 0,
        service_reserve: float = 0.02
    ) -> Dict:
        """
        计算完整报价
        
        Args:
            bom_cost: BOM成本
            product_type: 产品类型
            quantity: 数量
            customer_level: 客户等级
            rd_allocation: 研发分摊
            service_reserve: 售后预留率
            
        Returns:
            报价详情
        """
        # 基础价格
        base_price = self.calculate_base_price(bom_cost, product_type)
        
        # 应用折扣
        volume_discount = self.get_volume_discount(quantity)
        customer_discount = self.get_customer_discount(customer_level)
        
        # 调整后价格
        adjusted_price = base_price * volume_discount * customer_discount
        
        # 加上研发分摊
        adjusted_price += rd_allocation
        
        # 加上售后预留
        final_price = adjusted_price * (1 + service_reserve)
        
        return {
            'bom_cost': bom_cost,
            'base_price': base_price,
            'volume_discount': volume_discount,
            'customer_discount': customer_discount,
            'rd_allocation': rd_allocation,
            'service_reserve_rate': service_reserve,
            'final_unit_price': round(final_price, 2),
            'total_price': round(final_price * quantity, 2),
            'margin_rate': round(1 - bom_cost / final_price, 4),
            'breakdown': {
                '原材料成本': bom_cost,
                '基础毛利': base_price - bom_cost,
                '批量折扣': base_price * (1 - volume_discount),
                '客户折扣': base_price * volume_discount * (1 - customer_discount),
                '研发分摊': rd_allocation,
                '售后预留': adjusted_price * service_reserve
            }
        }


def main():
    """示例用法"""
    print("=" * 50)
    print("AI报价系统 - 价格预测模块")
    print("=" * 50)
    
    # 规则计算示例
    calculator = QuotationCalculator()
    
    result = calculator.calculate_quotation(
        bom_cost=8500,
        product_type='电机',
        quantity=50,
        customer_level='A',
        rd_allocation=200
    )
    
    print("\n规则计算示例:")
    print(f"  BOM成本: ¥{result['bom_cost']}")
    print(f"  最终单价: ¥{result['final_unit_price']}")
    print(f"  毛利率: {result['margin_rate']:.2%}")
    print(f"  总价(50台): ¥{result['total_price']}")


if __name__ == "__main__":
    main()
