-- ==========================================
-- 生产环境数据库初始化脚本
-- ==========================================

-- 用户权限数据库表结构

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    synology_username VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200),
    role VARCHAR(20) DEFAULT 'user' CHECK(role IN ('admin', 'user')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_users_synology_username ON users(synology_username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 权限操作日志表
CREATE TABLE IF NOT EXISTS permission_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(36),
    action VARCHAR(100),
    resource VARCHAR(200),
    result VARCHAR(20) CHECK(result IN ('allowed', 'denied')),
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_permission_logs_user_id ON permission_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_permission_logs_created_at ON permission_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_permission_logs_result ON permission_logs(result);

-- 工序照片表
CREATE TABLE IF NOT EXISTS process_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_serial VARCHAR(100) NOT NULL,
    process_step VARCHAR(100) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(200) NOT NULL,
    file_size INTEGER,
    captured_by VARCHAR(36),
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_at TIMESTAMP NULL,
    metadata TEXT,  -- JSON格式的元数据
    FOREIGN KEY (captured_by) REFERENCES users(id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_process_photos_product_serial ON process_photos(product_serial);
CREATE INDEX IF NOT EXISTS idx_process_photos_process_step ON process_photos(process_step);
CREATE INDEX IF NOT EXISTS idx_process_photos_captured_at ON process_photos(captured_at);

-- 工序配置表
CREATE TABLE IF NOT EXISTS process_configurations (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    order_index INTEGER DEFAULT 0,
    required BOOLEAN DEFAULT 1,
    photo_required BOOLEAN DEFAULT 1,
    estimated_duration INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_process_configurations_order_index ON process_configurations(order_index);

-- 配置变更历史表
CREATE TABLE IF NOT EXISTS config_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_type VARCHAR(50) NOT NULL,  -- 'project', 'process', etc.
    config_name VARCHAR(100) NOT NULL,
    change_type VARCHAR(20) NOT NULL,  -- 'create', 'update', 'delete'
    old_value TEXT,  -- JSON格式
    new_value TEXT,  -- JSON格式
    changed_by VARCHAR(36),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (changed_by) REFERENCES users(id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_config_history_config_type ON config_history(config_type);
CREATE INDEX IF NOT EXISTS idx_config_history_config_name ON config_history(config_name);
CREATE INDEX IF NOT EXISTS idx_config_history_changed_at ON config_history(changed_at);

-- ==========================================
-- 初始数据
-- ==========================================

-- 插入默认管理员用户（如果不存在）
-- 注意：实际的管理员账户应该在首次登录时通过群晖认证创建
INSERT OR IGNORE INTO users (id, synology_username, display_name, role, created_at)
VALUES ('00000000-0000-0000-0000-000000000001', 'admin', '系统管理员', 'admin', CURRENT_TIMESTAMP);

-- ==========================================
-- 视图定义
-- ==========================================

-- 用户活动统计视图
CREATE VIEW IF NOT EXISTS user_activity_stats AS
SELECT 
    u.id,
    u.synology_username,
    u.display_name,
    u.role,
    u.last_login_at,
    COUNT(DISTINCT pl.id) as total_operations,
    SUM(CASE WHEN pl.result = 'denied' THEN 1 ELSE 0 END) as denied_operations,
    MAX(pl.created_at) as last_operation_at
FROM users u
LEFT JOIN permission_logs pl ON u.id = pl.user_id
GROUP BY u.id, u.synology_username, u.display_name, u.role, u.last_login_at;

-- 工序照片统计视图
CREATE VIEW IF NOT EXISTS process_photo_stats AS
SELECT 
    product_serial,
    process_step,
    COUNT(*) as photo_count,
    MIN(captured_at) as first_photo_at,
    MAX(captured_at) as last_photo_at,
    SUM(file_size) as total_size
FROM process_photos
GROUP BY product_serial, process_step;

-- ==========================================
-- 触发器定义
-- ==========================================

-- 用户更新时间触发器
CREATE TRIGGER IF NOT EXISTS update_users_timestamp 
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- 工序配置更新时间触发器
CREATE TRIGGER IF NOT EXISTS update_process_configurations_timestamp 
AFTER UPDATE ON process_configurations
FOR EACH ROW
BEGIN
    UPDATE process_configurations SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ==========================================
-- 数据完整性检查
-- ==========================================

-- 检查是否有孤立的权限日志（用户已删除）
-- SELECT COUNT(*) FROM permission_logs WHERE user_id NOT IN (SELECT id FROM users);

-- 检查是否有孤立的照片记录（用户已删除）
-- SELECT COUNT(*) FROM process_photos WHERE captured_by NOT IN (SELECT id FROM users);
