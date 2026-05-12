# QRTestScanner 架构文档

## 数据分层架构

### 设计原则

**配置数据与业务数据分离**

- **配置数据（元数据）**：使用JSON文件存储
- **业务数据（交易数据）**：使用CSV + H2数据库存储

## 数据存储策略

### 配置层（Configuration Layer）

#### 项目信息
- **存储方式**：JSON文件
- **存储位置**：`files/projects.json`
- **管理器**：`ProjectManager.kt`
- **数据结构**：
  ```json
  {
    "projects": ["项目A", "项目B", "项目C"]
  }
  ```
- **访问频率**：低（偶尔添加新项目）
- **数据量**：小（几十个项目）
- **选择理由**：
  - ✅ 数据量小，JSON足够
  - ✅ 人工可读，易于编辑
  - ✅ 可直接复制备份
  - ✅ 可通过文件共享分发

#### 项目配置
- **存储方式**：JSON文件（每个项目一个文件）
- **存储位置**：`files/projects/项目名称.json`
- **管理器**：`ProjectConfigManager.kt`
- **数据结构**：
  ```json
  {
    "projectName": "柳工物流园双12控制器",
    "productTypes": [
      {
        "typeName": "电机控制器",
        "materials": [
          {
            "name": "控制板",
            "partNumber": "U12020034.A0"
          },
          {
            "name": "左侧电容板",
            "partNumber": "W12020035.A0"
          }
        ]
      }
    ]
  }
  ```
- **包含内容**：
  - 产品类型列表
  - 每个产品类型的物料清单
  - 物料名称和编号映射
- **访问频率**：中（选择项目时加载，修改配置时更新）
- **数据量**：小（每个配置文件几KB）
- **选择理由**：
  - ✅ 独立配置，易于迁移
  - ✅ JSON格式清晰，易于理解
  - ✅ 可手动编辑和复制
  - ✅ 项目间配置隔离

#### 测试人员信息
- **存储方式**：EncryptedSharedPreferences
- **管理器**：`PreferencesManager.kt`
- **数据结构**：
  ```json
  {
    "testers_json": "[\"胡涛\", \"朱志强\", \"张三\", \"李四\"]",
    "selected_tester": "胡涛"
  }
  ```
- **访问频率**：高（每次操作都需要读取）
- **数据量**：极小（十几个人员）
- **选择理由**：
  - ✅ 需要快速访问
  - ✅ 需要加密存储
  - ✅ 与应用设置一起管理
  - ✅ SharedPreferences性能最优

### 业务层（Business Layer）

#### 产品扫描记录
- **存储方式**：CSV文件 + H2数据库（可选）
- **存储位置**：
  - CSV: `csv/项目名称.csv`
  - H2: `database/records.h2.db`
- **管理器**：`UnifiedDataManager.kt`
- **数据结构**：
  ```kotlin
  data class ProductRecord(
      val productSerial: String,      // 产品序列号
      val productType: String,        // 产品类型（引用配置）
      val projectName: String,        // 项目名称（引用配置）
      val operator: String,           // 操作员（引用配置）
      val scanTime: Long,             // 扫描时间
      val materials: Map<String, String>  // 物料数据
  )
  ```
- **访问频率**：极高（持续写入，频繁查询）
- **数据量**：大（成百上千条记录）
- **选择理由**：
  - ✅ CSV保持兼容性和可读性
  - ✅ H2提供高性能查询
  - ✅ 双写保证数据安全
  - ✅ 可根据需要切换模式

## 数据引用关系

### 引用策略：字符串引用（非外键）

```kotlin
// 产品记录通过字符串引用配置数据
ProductRecord(
    productSerial = "1122",
    productType = "电机控制器",      // 字符串引用项目配置
    projectName = "柳工物流园双12控制器",  // 字符串引用项目列表
    operator = "胡涛",               // 字符串引用人员列表
    materials = mapOf(
        "控制板" to "U12020034.A0",  // 字符串引用物料配置
        "左侧电容板" to "W12020035.A0"
    )
)
```

### 数据完整性保证

虽然没有数据库级别的外键约束，但通过应用层验证保证数据完整性：

```kotlin
class DataValidator {
    fun validateProductRecord(record: ProductRecord): ValidationResult {
        // 验证项目是否存在
        // 验证产品类型是否存在
        // 验证操作员是否存在
        // 验证物料是否匹配配置
    }
}
```

## 存储模式

### 三种存储模式

#### 1. CSV Only（默认）
- **适用场景**：5人以下小团队
- **优势**：简单可靠，Excel直接打开
- **劣势**：查询慢，并发支持弱

#### 2. CSV + H2 双写
- **适用场景**：5-10人，测试阶段
- **优势**：数据双备份，查询快
- **劣势**：占用空间略大

#### 3. H2 Primary
- **适用场景**：10+人，大数据量
- **优势**：查询极快，并发强
- **劣势**：依赖数据库

### 模式切换流程

```
CSV Only
  ↓ 数据量增加
CSV + H2 双写（导入历史数据）
  ↓ 验证稳定性
H2 Primary（高性能模式）
```

## 性能对比

| 操作 | JSON | CSV | H2 |
|------|------|-----|-----|
| **读取配置** | 1ms | - | - |
| **查询单条记录** | - | 50ms | 1ms |
| **查询100条** | - | 200ms | 10ms |
| **插入记录** | - | 5ms | 2ms |
| **并发写入** | ❌ | ⚠️ | ✅ |

## 设计优势

### 1. 职责清晰
- 配置管理：`ProjectManager`, `ProjectConfigManager`, `PreferencesManager`
- 业务管理：`UnifiedDataManager`, `H2DatabaseManager`
- 数据验证：`DataValidator`

### 2. 易于维护
- 配置文件人工可读
- JSON易于编辑和备份
- 数据库提供高性能查询

### 3. 灵活扩展
- 配置可随时修改
- 存储模式可平滑切换
- 支持渐进式升级

### 4. 数据安全
- 配置文件可独立备份
- 双写模式保证不丢数据
- 应用层验证保证完整性

### 5. 向后兼容
- 默认CSV模式保持兼容
- JSON格式稳定
- 可随时回退

## 未来扩展

如果确实需要将配置数据放入数据库（不推荐），可以考虑：

### 场景1：项目数量超过100个
- **方案**：项目列表迁移到数据库
- **保留**：项目配置仍用JSON

### 场景2：需要复杂的配置查询
- **方案**：配置数据迁移到数据库
- **保留**：导出JSON作为备份

### 场景3：需要配置版本控制
- **方案**：添加配置历史表
- **技术**：Git + JSON更简单

## 结论

**当前架构（JSON配置 + CSV/H2业务数据）是最优方案**

原因：
1. ✅ 配置数据量小，JSON足够且更优
2. ✅ 业务数据量大，数据库优势明显
3. ✅ 职责清晰，易于维护
4. ✅ 灵活扩展，向后兼容
5. ✅ 性能均衡，成本最低

**不建议将配置数据放入数据库**，因为：
1. ❌ 增加复杂度
2. ❌ 失去人工可读性
3. ❌ 备份和迁移困难
4. ❌ 过度设计，收益小
5. ❌ 维护成本高

## 参考文档

- `ProjectManager.kt` - 项目管理
- `ProjectConfigManager.kt` - 项目配置管理
- `PreferencesManager.kt` - 测试人员管理
- `UnifiedDataManager.kt` - 业务数据管理
- `H2DatabaseManager.kt` - H2数据库管理
- `DataValidator.kt` - 数据验证
- `CHANGELOG.md` - 变更历史
