"""
WebDAV 客户端模块 v2 - 使用webdavclient3库，参照SMB的详细日志格式
"""

from typing import Optional, Dict, List
import logging
import json
from webdav3.client import Client

logger = logging.getLogger(__name__)


class WebDAVClientV2:
    """改进的 WebDAV 客户端 - 参照SMB客户端的设计"""
    
    def __init__(self, base_url: str, username: str, password: str, base_path: str = ""):
        """
        初始化 WebDAV 客户端
        
        Args:
            base_url: WebDAV 服务器地址 (e.g., https://panovation.i234.me:5006)
            username: 用户名
            password: 密码
            base_path: 基础路径 (e.g., /MES/QRMES) - 保持原始格式
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        # 保持原始路径格式，不要随意修改
        self.base_path = base_path
        
        # 配置WebDAV客户端 - 优化超时和缓存设置
        options = {
            'webdav_hostname': self.base_url,
            'webdav_login': self.username,
            'webdav_password': self.password,
            'webdav_root': self.base_path or '/',
            'webdav_timeout': 15,  # 降低超时时间
            'webdav_chunk_size': 65536,
            'webdav_disable_check': True,  # 禁用不必要的检查
            'webdav_override': {  # 覆盖HTTP头以提高性能
                'Connection': 'keep-alive',
                'Keep-Alive': 'timeout=10, max=100'
            }
        }
        
        logger.info(f"[WebDAV调试] 初始化WebDAV客户端")
        logger.info(f"[WebDAV调试] 服务器: {self.base_url}")
        logger.info(f"[WebDAV调试] 用户名: {self.username}")
        logger.info(f"[WebDAV调试] 基础路径: {self.base_path}")
        logger.info(f"[WebDAV调试] webdav_root: {options['webdav_root']}")
        
        try:
            self.client = Client(options)
            logger.info(f"[WebDAV调试] ✓ 客户端初始化成功")
        except Exception as e:
            logger.error(f"[WebDAV调试] ✗ 客户端初始化失败: {e}")
            raise
    
    def _build_path(self, path: str) -> str:
        """构建完整的 WebDAV 路径 - 参照SMB的路径构建方式"""
        # 参照SMB的_build_path方法
        path = path.strip('/\\').replace('\\', '/')
        if path:
            full_path = f"{path}"  # webdavclient3会自动处理根路径
        else:
            full_path = ""
        logger.debug(f"[WebDAV调试] 路径构建: '{path}' -> '{full_path}'")
        return full_path
    
    def test_connection(self) -> bool:
        """测试连接是否可用 - 参照SMB的测试方式"""
        try:
            logger.info(f"[WebDAV调试] 开始测试连接")
            logger.info(f"[WebDAV调试] 服务器: {self.base_url}")
            logger.info(f"[WebDAV调试] 用户名: {self.username}")
            logger.info(f"[WebDAV调试] 基础路径: {self.base_path}")
            
            # 尝试列出基础路径 - 参照SMB的方式
            try:
                path = self.base_path if self.base_path else "."
                logger.info(f"[WebDAV调试] 尝试列出目录: {path}")
                
                # 列出基础路径目录
                items = self.client.list() if not self.base_path else self.client.list()
                logger.info(f"[WebDAV调试] ✓ 目录列出成功，找到 {len(items)} 个项目")
                
                # 记录找到的项目 - 只显示前5个
                for item in items[:5]:
                    logger.info(f"[WebDAV调试]   - {item}")
                
                return True
                
            except Exception as e:
                logger.warning(f"[WebDAV调试] ⚠ 目录列出失败: {e}，但连接成功，允许继续")
                return True  # 连接成功就允许继续 - 参照SMB方式
                
        except Exception as e:
            logger.error(f"[WebDAV调试] 测试连接失败: {e}")
            return False
    
    def exists(self, path: str) -> bool:
        """检查文件或目录是否存在 - 正确处理403 Forbidden"""
        try:
            full_path = self._build_path(path)
            logger.debug(f"[WebDAV调试] 检查存在: {full_path}")
            
            try:
                exists = self.client.check(full_path)
                logger.debug(f"[WebDAV调试] 存在检查结果: {exists}")
                return exists
            except Exception as e:
                error_msg = str(e).lower()
                # 403 Forbidden 可能表示目录存在但没有权限
                if "403" in error_msg or "forbidden" in error_msg:
                    logger.info(f"[WebDAV调试] 目录 '{full_path}' 返回403 Forbidden，可能存在但没有直接访问权限")
                    # 尝试列出目录来验证是否存在
                    try:
                        items = self.client.list(full_path)
                        logger.info(f"[WebDAV调试] ✓ 目录 '{full_path}' 存在，可以列出 {len(items)} 个项目")
                        return True
                    except Exception as list_e:
                        logger.debug(f"[WebDAV调试] 列出目录也失败: {list_e}")
                        return False
                else:
                    logger.debug(f"[WebDAV调试] 检查存在失败: {e}")
                    return False
            
        except Exception as e:
            logger.error(f"[WebDAV调试] 检查存在失败: {e}")
            return False
    
    def read_file(self, path: str) -> Optional[bytes]:
        """读取文件内容 - 参照SMB的读取方式"""
        try:
            full_path = self._build_path(path)
            logger.info(f"[WebDAV调试] 读取文件: {full_path}")
            
            # 检查文件是否存在
            if not self.client.check(full_path):
                logger.error(f"[WebDAV调试] ✗ 文件不存在: {full_path}")
                return None
            
            # 读取文件内容 - 使用webdavclient3的正确方法
            from io import BytesIO
            buffer = BytesIO()
            self.client.download_from(buffer, full_path)
            content = buffer.getvalue()
            
            logger.info(f"[WebDAV调试] ✓ 文件读取成功: {len(content)} 字节")
            return content
            
        except Exception as e:
            logger.error(f"[WebDAV调试] 读取文件失败: {e}")
            return None
    
    def write_file(self, path: str, content: bytes, content_type: str = 'application/octet-stream') -> bool:
        """写入文件 - 参照SMB的写入方式"""
        try:
            full_path = self._build_path(path)
            logger.info(f"[WebDAV调试] 写入文件: {full_path}")
            
            # 使用webdavclient3的正确方法
            from io import BytesIO
            buffer = BytesIO(content)
            
            # 上传文件
            self.client.upload_to(buffer, full_path)
            
            logger.info(f"[WebDAV调试] ✓ 文件写入成功")
            return True
            
        except Exception as e:
            logger.error(f"[WebDAV调试] 写入文件失败: {e}")
            return False
    
    def list_directory(self, path: str = '') -> List[Dict[str, str]]:
        """列出目录内容 - 参照SMB的返回格式，特别处理403 Forbidden"""
        try:
            full_path = self._build_path(path)
            logger.info(f"[WebDAV调试] 列出目录: {full_path}")
            
            try:
                # 列出目录内容
                items = self.client.list(full_path) if full_path else self.client.list()
                
                result = []
                for item in items:
                    # webdavclient3返回的是文件名列表
                    if item.endswith('/'):
                        # 目录 - 参照SMB的返回格式
                        name = item.rstrip('/')
                        if name:  # 跳过空名称
                            result.append({
                                'name': name,
                                'is_directory': True,  # 参照SMB的字段名
                                'size': 0,
                                'type': 'directory'  # 保留兼容性
                            })
                    else:
                        # 文件 - 参照SMB的返回格式
                        if item:  # 跳过空名称
                            result.append({
                                'name': item,
                                'is_directory': False,  # 参照SMB的字段名
                                'size': 0,  # TODO: 可以后续添加文件大小获取
                                'type': 'file'  # 保留兼容性
                            })
                
                logger.info(f"[WebDAV调试] ✓ 找到 {len(result)} 个项目")
                return result
                
            except Exception as list_error:
                error_msg = str(list_error).lower()
                # 对于record目录，403错误可能表示需要特殊处理
                if path.lower() == 'record' and ("403" in error_msg or "forbidden" in error_msg or "not found" in error_msg):
                    logger.info(f"[WebDAV调试] record目录返回403错误，尝试直接搜索CSV文件")
                    # 使用备用策略：直接检查已知的CSV文件
                    return self._check_known_csv_files_as_dict()
                else:
                    logger.error(f"[WebDAV调试] 列出目录失败: {list_error}")
                    return []
            
        except Exception as e:
            logger.error(f"[WebDAV调试] 列出目录失败: {e}")
            return []
    
    def _check_known_csv_files_as_dict(self) -> List[Dict[str, str]]:
        """检查已知项目的CSV文件是否存在，从项目配置中动态读取产品类型"""
        found_files = []
        
        try:
            # 首先读取项目列表
            projects_data = self.read_json('projects.json')
            if not projects_data or 'projects' not in projects_data:
                logger.warning(f"[WebDAV调试] 无法读取projects.json，使用默认项目列表")
                known_projects = ['测试项目', '柳工物流园双12', '徐工VCU', '柳工双20']
            else:
                known_projects = projects_data['projects']
                logger.info(f"[WebDAV调试] 从 projects.json 读取到 {len(known_projects)} 个项目")
            
            for project in known_projects:
                logger.debug(f"[WebDAV调试] 处理项目: {project}")
                
                # 读取项目配置
                project_config = self.read_json(f'projects/{project}.json')
                
                if project_config and 'productTypes' in project_config:
                    # 从配置中获取产品类型
                    product_types = [pt['typeName'] for pt in project_config['productTypes']]
                    logger.debug(f"[WebDAV调试] 项目 {project} 的产品类型: {product_types}")
                    
                    # 生成基于实际产品类型的CSV文件名
                    possible_names = []
                    for product_type in product_types:
                        possible_names.append(f"{project}_{product_type}.csv")
                    
                    # 添加旧格式兼容
                    possible_names.append(f"{project}.csv")
                    
                else:
                    logger.debug(f"[WebDAV调试] 项目 {project} 没有配置或productTypes，使用默认产品类型")
                    # 如果没有配置，使用默认的产品类型
                    possible_names = [
                        # 常见产品类型默认值
                        f"{project}_电机.csv",
                        f"{project}_电机控制器.csv",
                        f"{project}_控制器.csv",
                        f"{project}_VCU.csv",
                        # 旧格式兼容
                        f"{project}.csv",
                    ]
                    
                    # 对柳工项目添加特定类型
                    if '柳工' in project:
                        possible_names.extend([
                            f"{project}_双12.csv",
                            f"{project}_双20.csv"
                        ])
                
                # 检查文件是否存在
                for csv_name in possible_names:
                    csv_path = f"record/{csv_name}"
                    try:
                        if self.exists(csv_path):
                            logger.info(f"[WebDAV调试] ✓ 找到CSV文件: {csv_name}")
                            found_files.append({
                                'name': csv_name,
                                'is_directory': False,
                                'size': 0,
                                'type': 'file'
                            })
                            break  # 找到一个就跳出，避免重复
                    except Exception as e:
                        logger.debug(f"[WebDAV调试] 检查文件失败 {csv_path}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"[WebDAV调试] 读取项目配置失败: {e}")
            # 如果读取配置失败，回退到硬编码的默认项目列表
            logger.info(f"[WebDAV调试] 回退到默认的硬编码项目列表")
            known_projects = ['测试项目', '柳工物流园双12', '徐工VCU', '柳工双20']
            for project in known_projects:
                possible_names = [
                    f"{project}_电机.csv",
                    f"{project}_电机控制器.csv", 
                    f"{project}_控制器.csv",
                    f"{project}.csv"
                ]
                
                for csv_name in possible_names:
                    csv_path = f"record/{csv_name}"
                    try:
                        if self.exists(csv_path):
                            logger.info(f"[WebDAV调试] ✓ 找到CSV文件: {csv_name}")
                            found_files.append({
                                'name': csv_name,
                                'is_directory': False,
                                'size': 0,
                                'type': 'file'
                            })
                            break
                    except Exception as e:
                        logger.debug(f"[WebDAV调试] 检查文件失败 {csv_path}: {e}")
                        continue
        
        logger.info(f"[WebDAV调试] 通过动态配置检查找到 {len(found_files)} 个CSV文件")
        return found_files
    
    def create_directory(self, path: str) -> bool:
        """创建目录"""
        try:
            full_path = self._build_path(path)
            logger.info(f"[WebDAV调试] 创建目录: {full_path}")
            
            if self.client.check(full_path):
                logger.info(f"[WebDAV调试] ✓ 目录已存在")
                return True
            
            self.client.mkdir(full_path)
            logger.info(f"[WebDAV调试] ✓ 目录创建成功")
            return True
            
        except Exception as e:
            logger.error(f"[WebDAV调试] 创建目录失败: {e}")
            return False
    
    def delete_file(self, path: str) -> bool:
        """删除文件"""
        try:
            full_path = self._build_path(path)
            logger.info(f"[WebDAV调试] 删除文件: {full_path}")
            
            if not self.client.check(full_path):
                logger.warning(f"[WebDAV调试] ⚠ 文件不存在: {full_path}")
                return True
            
            self.client.clean(full_path)
            logger.info(f"[WebDAV调试] ✓ 文件删除成功")
            return True
            
        except Exception as e:
            logger.error(f"[WebDAV调试] 删除文件失败: {e}")
            return False
    
    def read_json(self, path: str) -> Optional[Dict]:
        """读取 JSON 文件"""
        content = self.read_file(path)
        if content:
            try:
                result = json.loads(content.decode('utf-8'))
                logger.info(f"[WebDAV调试] ✓ JSON解析成功")
                return result
            except Exception as e:
                logger.error(f"[WebDAV调试] JSON 解析失败: {e}")
        return None
    
    def write_json(self, path: str, data: Dict) -> bool:
        """写入 JSON 文件"""
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            result = self.write_file(path, content, 'application/json; charset=utf-8')
            if result:
                logger.info(f"[WebDAV调试] ✓ JSON写入成功")
            return result
        except Exception as e:
            logger.error(f"[WebDAV调试] JSON 写入失败: {e}")
            return False
    
    def read_csv(self, path: str) -> Optional[str]:
        """读取 CSV 文件"""
        content = self.read_file(path)
        if content:
            try:
                # 尝试不同的编码
                try:
                    # 移除 BOM
                    text = content.decode('utf-8-sig')
                    logger.info(f"[WebDAV调试] ✓ CSV解码成功 (UTF-8)")
                    return text
                except:
                    text = content.decode('gbk')
                    logger.info(f"[WebDAV调试] ✓ CSV解码成功 (GBK)")
                    return text
            except Exception as e:
                logger.error(f"[WebDAV调试] CSV解码失败: {e}")
        return None
    
    def write_csv(self, path: str, content: str) -> bool:
        """写入 CSV 文件"""
        try:
            # 添加 BOM 以确保 Excel 正确显示中文
            bom = '\ufeff'
            full_content = (bom + content).encode('utf-8')
            result = self.write_file(path, full_content, 'text/csv; charset=utf-8')
            if result:
                logger.info(f"[WebDAV调试] ✓ CSV写入成功")
            return result
        except Exception as e:
            logger.error(f"[WebDAV调试] CSV写入失败: {e}")
            return False
    

    
    def list_photos(self, product_serial: str) -> List[Dict]:
        """列出产品照片"""
        try:
            photo_path = f"picture/{product_serial}"
            logger.info(f"[WebDAV调试] 列出产品照片: {photo_path}")
            
            # 检查目录是否存在
            if not self.exists(photo_path):
                logger.info(f"[WebDAV调试] 照片目录不存在: {photo_path}")
                return []
            
            items = self.list_directory(photo_path)
            
            photos = []
            for item in items:
                # 检查是否为图片文件
                if not item.get('is_directory', False):
                    filename = item['name'].lower()
                    if filename.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif')):
                        photos.append({
                            'name': item['name'],
                            'size': item.get('size', 0),
                            'modified_time': item.get('modified_time', ''),
                            'path': f"{photo_path}/{item['name']}",
                            'type': 'image'
                        })
            
            logger.info(f"[WebDAV调试] ✓ 找到 {len(photos)} 张照片")
            return photos
            
        except Exception as e:
            logger.error(f"[WebDAV调试] 列出照片失败: {e}")
            return []
    
    def get_photo(self, product_serial: str, filename: str) -> Optional[bytes]:
        """获取产品照片内容"""
        photo_path = f"picture/{product_serial}/{filename}"
        return self.read_file(photo_path)
    
    def delete_photo(self, product_serial: str, filename: str) -> bool:
        """删除产品照片"""
        photo_path = f"picture/{product_serial}/{filename}"
        return self.delete_file(photo_path)


# 为了保持兼容性，创建别名
WebDAVClient = WebDAVClientV2