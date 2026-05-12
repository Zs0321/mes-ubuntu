# Android Studio 布局调整指南

## 📱 如何在 Android Studio 中调整主页布局

### 1. 打开布局文件

#### 方法一：通过项目结构导航
1. 在 Android Studio 左侧的 **Project** 面板中
2. 展开 `app` → `src` → `main` → `res` → `layout`
3. 双击 `activity_main.xml` 文件

#### 方法二：快速搜索
1. 按 `Ctrl + Shift + N` (Windows) 或 `Cmd + Shift + O` (Mac)
2. 输入 `activity_main.xml`
3. 按回车打开

### 2. 布局编辑器界面

打开布局文件后，你会看到三种视图模式（右上角切换）：

- **Design（设计视图）**：可视化拖拽界面
- **Split（分屏视图）**：同时显示设计和代码
- **Code（代码视图）**：纯 XML 代码编辑

**推荐使用 Split 视图**，可以同时看到效果和代码。

### 3. 当前主页布局结构

```
LinearLayout (垂直布局)
├── MaterialToolbar (顶部工具栏)
├── TabLayout (选项卡：物料记录/工序记录)
├── 同步进度指示器
├── 产品信息区
│   ├── 产品类型
│   └── 产品型号
├── 项目信息区
│   ├── 项目号
│   └── 项目名称
├── 扫描按钮组
│   ├── 扫描产品二维码按钮
│   └── 手动输入按钮
└── 产品信息展示区 (动态显示)
    ├── 产品序列号卡片
    └── 子零部件列表
```

### 4. 常见布局调整操作

#### 4.1 调整控件间距

**在 Design 视图中：**
1. 点击选中要调整的控件
2. 在右侧 **Attributes** 面板中找到 `Layout_Margin`
3. 调整 `top`、`bottom`、`start`、`end` 的值

**在 Code 视图中：**
```xml
<LinearLayout
    android:layout_marginTop="16dp"
    android:layout_marginBottom="16dp"
    android:layout_marginStart="8dp"
    android:layout_marginEnd="8dp">
```

#### 4.2 调整控件大小

**宽度和高度属性：**
- `match_parent`：填充父容器
- `wrap_content`：根据内容自适应
- 具体数值：如 `48dp`、`100dp`

**示例：**
```xml
<Button
    android:layout_width="match_parent"
    android:layout_height="60dp" />
```

#### 4.3 调整文字大小和颜色

```xml
<TextView
    android:textSize="16sp"
    android:textColor="#000000"
    android:textStyle="bold" />
```

#### 4.4 调整按钮样式

```xml
<com.google.android.material.button.MaterialButton
    android:layout_width="wrap_content"
    android:layout_height="60dp"
    android:text="按钮文字"
    android:textSize="16sp"
    app:cornerRadius="12dp"
    app:icon="@drawable/ic_icon"
    app:iconSize="24dp" />
```

#### 4.5 隐藏或显示控件

**在 XML 中：**
```xml
<!-- 完全隐藏，不占空间 -->
android:visibility="gone"

<!-- 隐藏但占空间 -->
android:visibility="invisible"

<!-- 显示 -->
android:visibility="visible"
```

### 5. 实用调整示例

#### 示例 1：增大扫描按钮

**修改前：**
```xml
<com.google.android.material.button.MaterialButton
    android:id="@+id/btnScanProduct"
    android:layout_height="60dp" />
```

**修改后：**
```xml
<com.google.android.material.button.MaterialButton
    android:id="@+id/btnScanProduct"
    android:layout_height="80dp"
    android:textSize="18sp" />
```

#### 示例 2：调整产品信息区布局

**改为卡片样式：**
```xml
<com.google.android.material.card.MaterialCardView
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:layout_marginBottom="16dp"
    app:cardCornerRadius="12dp"
    app:cardElevation="4dp">
    
    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="vertical"
        android:padding="16dp">
        
        <!-- 产品类型和型号 -->
        
    </LinearLayout>
</com.google.android.material.card.MaterialCardView>
```

#### 示例 3：改变按钮排列方式

**从横向改为纵向：**
```xml
<!-- 修改前：横向排列 -->
<LinearLayout
    android:orientation="horizontal">
    <Button ... />
    <Button ... />
</LinearLayout>

<!-- 修改后：纵向排列 -->
<LinearLayout
    android:orientation="vertical">
    <Button ... />
    <Button ... />
</LinearLayout>
```

#### 示例 4：添加新的控件

**在 Design 视图中：**
1. 从左侧 **Palette** 面板拖拽控件到布局中
2. 常用控件：
   - `TextView`：文本显示
   - `Button`：按钮
   - `EditText`：输入框
   - `ImageView`：图片
   - `RecyclerView`：列表

**在 Code 视图中：**
```xml
<TextView
    android:id="@+id/tvNewLabel"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:text="新增的文本"
    android:textSize="14sp"
    android:layout_marginTop="8dp" />
```

### 6. 预览和测试

#### 6.1 实时预览
- 在 Design 或 Split 视图中，右侧会实时显示布局效果
- 可以切换不同设备预览（顶部工具栏）

#### 6.2 在模拟器中测试
1. 点击顶部工具栏的 **Run** 按钮（绿色三角形）
2. 或按 `Shift + F10` (Windows) 或 `Ctrl + R` (Mac)
3. 选择模拟器或真机运行

### 7. 常用快捷键

| 操作 | Windows/Linux | Mac |
|------|---------------|-----|
| 格式化代码 | `Ctrl + Alt + L` | `Cmd + Option + L` |
| 查找文件 | `Ctrl + Shift + N` | `Cmd + Shift + O` |
| 查找类 | `Ctrl + N` | `Cmd + O` |
| 运行应用 | `Shift + F10` | `Ctrl + R` |
| 代码补全 | `Ctrl + Space` | `Ctrl + Space` |
| 查看文档 | `Ctrl + Q` | `F1` |

### 8. 布局调试技巧

#### 8.1 使用 Layout Inspector
1. 运行应用到模拟器或真机
2. 点击 `Tools` → `Layout Inspector`
3. 选择运行中的进程
4. 可以查看实时的布局层级和属性

#### 8.2 显示布局边界
1. 在设备上打开 **开发者选项**
2. 启用 **显示布局边界**
3. 可以看到所有控件的边界框

### 9. 常见问题解决

#### 问题 1：控件重叠
**解决方法：**
- 检查 `layout_margin` 和 `padding` 设置
- 确保父容器有足够空间
- 使用 `ConstraintLayout` 替代 `LinearLayout`

#### 问题 2：文字被截断
**解决方法：**
```xml
<TextView
    android:layout_width="0dp"
    android:layout_weight="1"
    android:ellipsize="end"
    android:maxLines="1" />
```

#### 问题 3：按钮太小点不到
**解决方法：**
```xml
<Button
    android:minHeight="48dp"
    android:minWidth="48dp" />
```

### 10. 推荐的布局优化

#### 10.1 使用 ConstraintLayout
`ConstraintLayout` 比 `LinearLayout` 更灵活，性能更好：

```xml
<androidx.constraintlayout.widget.ConstraintLayout
    android:layout_width="match_parent"
    android:layout_height="match_parent">
    
    <Button
        android:id="@+id/button"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        app:layout_constraintTop_toTopOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent" />
        
</androidx.constraintlayout.widget.ConstraintLayout>
```

#### 10.2 使用 Material Design 组件
项目已经使用了 Material Design，继续使用这些组件：
- `MaterialButton`
- `MaterialCardView`
- `TextInputLayout`
- `MaterialToolbar`

### 11. 修改后的操作流程

1. **修改 XML 文件**
   - 在 `activity_main.xml` 中修改布局

2. **保存文件**
   - `Ctrl + S` (Windows) 或 `Cmd + S` (Mac)

3. **构建项目**
   - `Build` → `Make Project`
   - 或按 `Ctrl + F9` (Windows) 或 `Cmd + F9` (Mac)

4. **运行测试**
   - 点击 Run 按钮或按 `Shift + F10`

5. **查看效果**
   - 在模拟器或真机上查看实际效果

### 12. 实战练习建议

#### 练习 1：调整按钮大小
- 将扫描按钮高度从 60dp 改为 80dp
- 增大按钮文字到 18sp

#### 练习 2：添加间距
- 在产品信息区和项目信息区之间增加 24dp 间距

#### 练习 3：改变颜色
- 修改工具栏背景色
- 修改按钮颜色

#### 练习 4：添加图标
- 为产品类型和项目名称添加图标

### 13. 相关文件位置

- **布局文件**: `app/src/main/res/layout/activity_main.xml`
- **Activity 代码**: `app/src/main/java/com/testcenter/qrscanner/MainActivity.kt`
- **颜色定义**: `app/src/main/res/values/colors.xml`
- **字符串资源**: `app/src/main/res/values/strings.xml`
- **样式定义**: `app/src/main/res/values/styles.xml`

### 14. 在线资源

- [Android 官方文档 - 布局](https://developer.android.com/guide/topics/ui/declaring-layout)
- [Material Design 组件](https://material.io/components)
- [ConstraintLayout 指南](https://developer.android.com/training/constraint-layout)

---

## 💡 小贴士

1. **经常保存**：修改后及时保存，避免丢失工作
2. **小步迭代**：每次只修改一小部分，立即测试
3. **使用版本控制**：修改前先提交当前版本，方便回退
4. **参考现有代码**：查看其他布局文件学习最佳实践
5. **使用预览功能**：充分利用 Android Studio 的实时预览

## 🎯 快速开始

如果你想快速调整主页布局，建议：

1. 打开 `activity_main.xml`
2. 切换到 **Split** 视图
3. 在右侧预览中选择你的目标设备
4. 在左侧代码中修改，右侧实时查看效果
5. 满意后运行到真机测试

祝你调整顺利！如果遇到问题，随时问我。
