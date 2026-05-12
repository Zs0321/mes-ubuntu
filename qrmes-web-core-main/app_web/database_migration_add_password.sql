-- 数据库迁移脚本：添加密码字段
-- 用于支持本地认证，移除群晖依赖

-- 1. 添加密码字段到用户表
ALTER TABLE users ADD COLUMN password_hash TEXT;

-- 2. 添加密码盐值字段
ALTER TABLE users ADD COLUMN password_salt TEXT;

-- 3. 添加是否启用字段
ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1;

-- 4. 创建索引
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- 5. 为现有管理员设置默认密码（admin123）
-- 密码哈希: SHA256("admin123")
UPDATE users 
SET password_hash = '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9',
    password_salt = '',
    is_active = 1
WHERE role = 'admin' AND password_hash IS NULL;

-- 6. 显示更新结果
SELECT 
    synology_username as '用户名',
    display_name as '显示名',
    role as '角色',
    CASE WHEN password_hash IS NOT NULL THEN '已设置' ELSE '未设置' END as '密码状态',
    CASE WHEN is_active = 1 THEN '启用' ELSE '禁用' END as '状态'
FROM users;
