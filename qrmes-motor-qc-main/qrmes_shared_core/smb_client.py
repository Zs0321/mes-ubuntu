"""
SMB 客户端模块 - 用于访问 Windows 共享文件夹
"""

from typing import Optional, Dict, List
import logging
from smb.SMBConnection import SMBConnection
from smb import smb_structs
import tempfile
import io
import traceback

logger = logging.getLogger(__name__)

# 禁用 pysmb 的详细日志
logging.getLogger('SMB.SMBConnection').setLevel(logging.WARNING)


class SMBClient:
    """改进的 SMB 客户端 - 优化连接管理"""
    
    def __init__(self, server: str, share_name: str, username: str, password: str, base_path: str = ""):
        """
        初始化 SMB 客户端
        
        Args:
            server: SMB 服务器地址 (e.g., 172.16.30.2)
            share_name: 共享名称 (e.g., mes)
            username: 用户名
            password: 密码
            base_path: 基础路径 (e.g., QRMES)
        """
        self.server = server
        self.share_name = share_name
        self.username = username
        self.password = password
        self.base_path = base_path.strip('/\\').replace('/', '\\')
        self.conn: Optional[SMBConnection] = None
        self._connection_active = False
        
    def _build_path(self, path: str) -> str:
        """构建完整的 SMB 路径"""
        path = path.strip('/\\').replace('/', '\\')
        if self.base_path:
            full_path = f"{self.base_path}\\{path}" if path else self.base_path
        else:
            full_path = path
        return full_path
    
    def connect(self) -> bool:
        """建立 SMB 连接"""
        try:
            # 如果已经连接，尝试重用
            if self.conn and self._connection_active:
                try:
                    # 简单测试连接是否有效
                    if self.conn:
                        self.conn.listPath(self.share_name, self.base_path or '.')
                    logger.debug(f"[SMB调试] ✓ 重用现有连接")
                    return True
                except:
                    logger.debug(f"[SMB调试] 现有连接无效，重新连接")
                    self._connection_active = False
            
            logger.info(f"[SMB调试] 连接到 SMB 服务器: {self.server}, 共享: {self.share_name}")
            
            # 创建新的 SMB 连接
            self.conn = SMBConnection(
                self.username,
                self.password,
                'python-client',  # client machine name
                self.server,       # server name
                use_ntlm_v2=True
            )
            
            # 连接到服务器
            connected = self.conn.connect(self.server, 445, timeout=10)
            
            if connected:
                self._connection_active = True
                logger.info(f"[SMB调试] ✓ SMB 连接成功")
                return True
            else:
                self._connection_active = False
                logger.error(f"[SMB调试] ✗ SMB 连接失败")
                return False
                
        except Exception as e:
            self._connection_active = False
            logger.error(f"[SMB调试] 连接异常: {e}")
            return False
    
    def disconnect(self):
        """断开 SMB 连接"""
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
    
    def test_connection(self) -> bool:
        """测试连接是否可用"""
        try:
            logger.info(f"[SMB调试] 开始测试连接")
            logger.info(f"[SMB调试] 服务器: {self.server}, 共享: {self.share_name}")
            logger.info(f"[SMB调试] 用户名: {self.username}")
            logger.info(f"[SMB调试] 基础路径: {self.base_path}")
            
            if not self.connect():
                return False
            
            # 尝试列出基础路径
            try:
                path = self.base_path if self.base_path else "."
                logger.info(f"[SMB调试] 尝试列出目录: {path}")
                files = self.conn.listPath(self.share_name, path)
                logger.info(f"[SMB调试] ✓ 目录列出成功，找到 {len(files)} 个项目")
                return True
            except Exception as e:
                logger.warning(f"[SMB调试] ⚠ 目录列出失败: {e}，但连接成功，允许继续")
                return True  # 连接成功就允许继续
                
        except Exception as e:
            logger.error(f"[SMB调试] 测试连接失败: {e}")
            return False
        finally:
            self.disconnect()
    
    def exists(self, path: str) -> bool:
        """检查文件或目录是否存在"""
        try:
            full_path = self._build_path(path)
            if not self.conn:
                if not self.connect():
                    return False
            
            try:
                if self.conn:
                    self.conn.getAttributes(self.share_name, full_path)
                    return True
                return False
            except:
                return False
        except:
            return False
    
    def read_file(self, path: str) -> Optional[bytes]:
        """读取文件内容"""
        try:
            full_path = self._build_path(path)
            logger.info(f"[SMB调试] 读取文件: {full_path}")
            
            # 确保连接有效
            if not self.connect():
                logger.error(f"[SMB调试] 连接失败，无法读取文件")
                return None
            
            # 读取文件到内存
            file_obj = io.BytesIO()
            if self.conn:
                self.conn.retrieveFile(self.share_name, full_path, file_obj)
            content = file_obj.getvalue()
            
            logger.info(f"[SMB调试] ✓ 文件读取成功: {len(content)} 字节")
            return content
            
        except Exception as e:
            logger.error(f"[SMB调试] 读取文件失败: {e}")
            # 如果读取失败，标记连接为无效
            self._connection_active = False
            return None
        # 注意：不再在 finally 中断开连接
    
    def write_file(self, path: str, content: bytes) -> bool:
        """写入文件"""
        try:
            full_path = self._build_path(path)
            logger.info(f"[SMB调试] 写入文件: {full_path}")
            
            # 检查连接状态
            logger.info(f"[SMB调试] 当前连接状态: conn={self.conn is not None}, active={self._connection_active}")
            
            # 确保连接有效
            if not self.connect():
                logger.error(f"[SMB调试] 连接失败，无法写入文件")
                return False
            
            logger.info(f"[SMB调试] 连接检查后状态: conn={self.conn is not None}, active={self._connection_active}")
            
            # 自动创建父目录
            parent_dir = '\\'.join(full_path.split('\\')[:-1])
            if parent_dir and parent_dir != full_path:
                logger.info(f"[SMB调试] 检查父目录: {parent_dir}")
                try:
                    # 检查父目录是否存在
                    if self.conn:
                        self.conn.listPath(self.share_name, parent_dir)
                    logger.debug(f"[SMB调试] 父目录已存在: {parent_dir}")
                except:
                    # 父目录不存在，尝试创建
                    logger.info(f"[SMB调试] 父目录不存在，尝试创建: {parent_dir}")
                    parent_parts = parent_dir.split('\\')
                    current_path = ""
                    
                    for part in parent_parts:
                        if not part:
                            continue
                        if current_path:
                            current_path += "\\" + part
                        else:
                            current_path = part
                        
                        try:
                            if self.conn:
                                self.conn.listPath(self.share_name, current_path)
                            logger.debug(f"[SMB调试] 目录已存在: {current_path}")
                        except:
                            try:
                                logger.info(f"[SMB调试] 创建目录: {current_path}")
                                if self.conn:
                                    self.conn.createDirectory(self.share_name, current_path)
                                logger.info(f"[SMB调试] ✓ 目录创建成功: {current_path}")
                            except Exception as create_e:
                                logger.warning(f"[SMB调试] 创建目录失败 {current_path}: {create_e}")
            
            # 写入文件
            logger.info(f"[SMB调试] 开始写入文件，连接状态: {self.conn is not None}")
            file_obj = io.BytesIO(content)
            if self.conn:
                self.conn.storeFile(self.share_name, full_path, file_obj)
            else:
                logger.error(f"[SMB调试] 连接为空，无法写入文件")
                return False
            
            logger.info(f"[SMB调试] ✓ 文件写入成功")
            return True
            
        except Exception as e:
            logger.error(f"[SMB调试] 写入文件失败: {e}")
            logger.error(f"[SMB调试] 错误详情: {traceback.format_exc()}")
            # 如果写入失败，标记连接为无效
            self._connection_active = False
            return False
        # 注意：不再在 finally 中断开连接
    
    def list_directory(self, path: str = '') -> List[Dict]:
        """列出目录内容"""
        try:
            full_path = self._build_path(path) if path else self.base_path
            logger.info(f"[SMB调试] 列出目录: {full_path}")
            
            # 确保连接有效
            if not self.connect():
                logger.error(f"[SMB调试] 连接失败，无法列出目录")
                return []
            
            files = self.conn.listPath(self.share_name, full_path)
            items = []
            
            for f in files:
                if f.filename in ['.', '..']:
                    continue
                    
                items.append({
                    'name': f.filename,
                    'is_directory': f.isDirectory,
                    'size': f.file_size if not f.isDirectory else 0
                })
            
            logger.info(f"[SMB调试] ✓ 找到 {len(items)} 个项目")
            return items
            
        except Exception as e:
            logger.error(f"[SMB调试] 列出目录失败: {e}")
            # 如果列目录失败，标记连接为无效
            self._connection_active = False
            return []
        # 注意：不再在 finally 中断开连接
    
    def read_json(self, path: str) -> Optional[Dict]:
        """读取 JSON 文件"""
        content = self.read_file(path)
        if content:
            try:
                import json
                # 兼容 NAS 侧 UTF-8 BOM/UTF-8/GBK 文件
                try:
                    text = content.decode('utf-8-sig')
                except UnicodeDecodeError:
                    text = content.decode('utf-8')
                return json.loads(text)
            except UnicodeDecodeError:
                try:
                    import json
                    return json.loads(content.decode('gbk'))
                except Exception as e:
                    logger.error(f"[SMB调试] JSON 解析失败(GBK回退): {e}")
            except Exception as e:
                logger.error(f"[SMB调试] JSON 解析失败: {e}")
        return None
    
    def write_json(self, path: str, data: Dict) -> bool:
        """写入 JSON 文件"""
        try:
            import json
            content = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            return self.write_file(path, content)
        except Exception as e:
            logger.error(f"[SMB调试] JSON 写入失败: {e}")
            return False
    
    def read_csv(self, path: str) -> Optional[str]:
        """读取 CSV 文件"""
        content = self.read_file(path)
        if content:
            try:
                # 尝试 UTF-8 with BOM
                if content.startswith(b'\xef\xbb\xbf'):
                    return content[3:].decode('utf-8')
                return content.decode('utf-8')
            except:
                try:
                    return content.decode('gbk')
                except:
                    return None
        return None
    
    def create_directory(self, path: str) -> bool:
        """创建目录"""
        try:
            full_path = self._build_path(path)
            logger.info(f"[SMB调试] 创建目录: {full_path}")
            
            if not self.conn:
                if not self.connect():
                    return False
            
            # 在SMB中创建目录，需要逐级创建父目录
            path_parts = full_path.split('\\')
            current_path = ""
            
            for part in path_parts:
                if not part:  # 跳过空部分
                    continue
                    
                if current_path:
                    current_path += "\\" + part
                else:
                    current_path = part
                
                try:
                    # 检查目录是否存在
                    try:
                        if self.conn:
                            self.conn.listPath(self.share_name, current_path)
                        logger.debug(f"[SMB调试] 目录已存在: {current_path}")
                    except:
                        # 目录不存在，创建它
                        logger.info(f"[SMB调试] 创建子目录: {current_path}")
                        if self.conn:
                            self.conn.createDirectory(self.share_name, current_path)
                        logger.info(f"[SMB调试] ✓ 子目录创建成功: {current_path}")
                except Exception as e:
                    logger.warning(f"[SMB调试] 创建子目录失败 {current_path}: {e}")
                    # 继续尝试下一个目录
            
            logger.info(f"[SMB调试] ✓ 目录创建操作完成: {full_path}")
            return True
            
        except Exception as e:
            logger.error(f"[SMB调试] 创建目录失败: {e}")
            self._connection_active = False
            return False
        # 注意：不再在 finally 中断开连接
    
    def delete_file(self, path: str) -> bool:
        """删除文件"""
        try:
            full_path = self._build_path(path)
            logger.info(f"[SMB调试] 删除文件: {full_path}")
            
            if not self.conn:
                if not self.connect():
                    return False
            
            self.conn.deleteFiles(self.share_name, full_path)
            logger.info(f"[SMB调试] ✓ 文件删除成功")
            return True
            
        except Exception as e:
            logger.error(f"[SMB调试] 删除文件失败: {e}")
            return False
        finally:
            self.disconnect()
    
    def list_photos(self, product_serial: str) -> List[Dict]:
        """列出产品照片"""
        try:
            photo_path = f"picture\\{product_serial}"
            full_path = self._build_path(photo_path)
            logger.info(f"[SMB调试] 列出产品照片: {full_path}")
            
            if not self.connect():
                logger.error(f"[SMB调试] 连接失败，无法列出照片")
                return []
            
            files = self.conn.listPath(self.share_name, full_path)
            
            photos = []
            for file_info in files:
                if not file_info.isDirectory and file_info.filename not in ['.', '..']:
                    # 检查是否为图片文件
                    filename = file_info.filename.lower()
                    if filename.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif')):
                        photos.append({
                            'name': file_info.filename,
                            'size': file_info.file_size,
                            'modified_time': file_info.last_write_time,
                            'path': f"{photo_path}\\{file_info.filename}",
                            'type': 'image'
                        })
            
            logger.info(f"[SMB调试] ✓ 找到 {len(photos)} 张照片")
            return photos
            
        except Exception as e:
            logger.error(f"[SMB调试] 列出照片失败: {e}")
            return []
        finally:
            self.disconnect()
    
    def get_photo(self, product_serial: str, filename: str) -> Optional[bytes]:
        """获取产品照片内容"""
        photo_path = f"picture/{product_serial}/{filename}"
        return self.read_file(photo_path)
    
    def delete_photo(self, product_serial: str, filename: str) -> bool:
        """删除产品照片"""
        photo_path = f"picture/{product_serial}/{filename}"
        return self.delete_file(photo_path)
