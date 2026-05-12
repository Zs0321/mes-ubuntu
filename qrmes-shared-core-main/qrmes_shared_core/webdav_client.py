"""
WebDAV 客户端模块
"""

from typing import Optional, Dict, List
import logging
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, quote, unquote
import json

logger = logging.getLogger(__name__)


class WebDAVClient:
    """WebDAV 客户端"""
    
    def __init__(self, base_url: str, username: str, password: str, base_path: str = ""):
        """
        初始化 WebDAV 客户端
        
        Args:
            base_url: WebDAV 服务器地址 (e.g., https://panovation.i234.me:5006)
            username: 用户名
            password: 密码
            base_path: 基础路径 (e.g., /测试中心/17、工时管理)
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.base_path = base_path.rstrip('/')
        self.auth = HTTPBasicAuth(username, password)
        self.session = requests.Session()
        self.session.auth = self.auth
        # 添加 Windows WebDAV 兼容头
        self.session.headers.update({
            'User-Agent': 'Microsoft-WebDAV-MiniRedir/10.0.19041',
            'Translate': 'f',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Accept': '*/*',
            'Connection': 'Keep-Alive'
        })
    
    def _build_url(self, path: str) -> str:
        """构建完整的 URL"""
        # 移除开头的斜杠
        path = path.lstrip('/')
        
        # 组合基础路径和文件路径
        if self.base_path:
            # 确保 base_path 以 / 开头
            base = self.base_path if self.base_path.startswith('/') else f'/{self.base_path}'
            # 组合路径，确保正确的路径格式
            if path:
                full_path = f"{base}/{path}"
            else:
                full_path = base
        else:
            full_path = f"/{path}" if path else "/"
        
        # 保持原始路径结构，不做复杂的URL编码
        # 只对中文等特殊字符编码
        parts = full_path.split('/')
        encoded_parts = []
        for part in parts:
            if part:  # 跳过空字符串
                # 只对非 ASCII 字符编码
                if any(ord(c) > 127 for c in part):
                    encoded_parts.append(quote(part, safe=''))
                else:
                    encoded_parts.append(part)
            else:
                encoded_parts.append('')  # 保持空字符串以维持路径结构
        
        encoded_path = '/'.join(encoded_parts)
        
        return f"{self.base_url}{encoded_path}"
    
    def test_connection(self) -> bool:
        """测试连接是否可用，尝试多个可能的路径前缀"""
        root_auth_success = False  # 初始化根路径认证状态
        
        try:
            logger.info(f"[WebDAV调试] 开始测试连接")
            logger.info(f"[WebDAV调试] 用户名: {self.username}")
            logger.info(f"[WebDAV调试] 基础路径: {self.base_path}")
            
            # 首先测试根路径认证
            root_url = f"{self.base_url}/"
            logger.info(f"[WebDAV调试] 测试根路径认证: {root_url}")
            response = self.session.request('PROPFIND', root_url, headers={'Depth': '0'}, timeout=10)
            logger.info(f"[WebDAV调试] 根路径响应状态码: {response.status_code}")
            
            if response.status_code == 401:
                logger.error(f"[WebDAV调试] 认证失败 (401 Unauthorized) - 用户名或密码错误")
                return False
            elif response.status_code in [200, 207]:
                logger.info(f"[WebDAV调试] ✓ 根路径认证成功")
                # 根路径认证成功就足够了，即使子路径验证失败也允许继续
                root_auth_success = True
            else:
                root_auth_success = False
            
            # 如果根路径认证通过，尝试访问 base_path 下的文件
            # Android 应用直接访问文件，不使用 PROPFIND 检查目录
            path_candidates = [
                f"{self.base_path}/record/",  # 尝试 record 目录
                f"/dav{self.base_path}/record/",
                f"/webdav{self.base_path}/record/",
                f"{self.base_path}/",  # 尝试基础目录
                f"/dav{self.base_path}/",
                f"/webdav{self.base_path}/"
            ]
            
            for test_path in path_candidates:
                url = f"{self.base_url}{test_path}"
                logger.info(f"[WebDAV调试] 尝试路径: {url}")
                
                # 使用 PROPFIND 测试目录
                response = self.session.request('PROPFIND', url, headers={'Depth': '0'}, timeout=10)
                logger.info(f"[WebDAV调试] 响应状态码: {response.status_code}")
                
                # 200, 207 (Multi-Status), 404 都算可以继续
                # 405 (Method Not Allowed) 说明路径可能存在但不支持 PROPFIND
                if response.status_code in [200, 207]:
                    logger.info(f"[WebDAV调试] ✓ 连接成功！使用路径: {test_path}")
                    # 更新 base_path（去掉末尾的斜杠和 /record）
                    if test_path.endswith('/record/'):
                        self.base_path = test_path[:-8]  # 去掉 '/record/'
                    else:
                        self.base_path = test_path.rstrip('/')
                    return True
                elif response.status_code == 404:
                    logger.info(f"[WebDAV调试] ✗ 路径不存在 (404)")
                elif response.status_code == 405:
                    # 405 说明路径可能存在，但不支持 PROPFIND
                    # 尝试用 GET 请求测试
                    logger.info(f"[WebDAV调试] ⚠ PROPFIND 不支持，尝试 GET 请求")
                    get_response = self.session.get(url, timeout=10)
                    logger.info(f"[WebDAV调试] GET 响应状态码: {get_response.status_code}")
                    if get_response.status_code in [200, 301, 302, 403]:  # 403 说明路径存在但无权限列表
                        logger.info(f"[WebDAV调试] ✓ 路径可访问！使用路径: {test_path}")
                        if test_path.endswith('/record/'):
                            self.base_path = test_path[:-8]
                        else:
                            self.base_path = test_path.rstrip('/')
                        return True
            
            # 所有子路径都失败，但如果根路径认证成功，允许继续
            if root_auth_success:
                logger.warning(f"[WebDAV调试] ⚠ 子路径验证失败，但根路径认证成功，允许继续")
                logger.warning(f"[WebDAV调试] 将使用配置的基础路径: {self.base_path}")
                return True
            
            logger.error(f"[WebDAV调试] 所有路径尝试都失败，且根路径认证也失败")
            return False
            
        except requests.exceptions.ConnectTimeout as e:
            logger.error(f"[WebDAV调试] 连接超时: {e}")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[WebDAV调试] 连接错误: {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"[WebDAV调试] 请求异常: {e}")
            return False
        except Exception as e:
            logger.error(f"[WebDAV调试] 连接测试失败: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[WebDAV调试] 堆栈跟踪:\n{traceback.format_exc()}")
            return False
    
    def exists(self, path: str) -> bool:
        """检查文件或目录是否存在"""
        try:
            url = self._build_url(path)
            response = self.session.request('PROPFIND', url, headers={'Depth': '0'}, timeout=10)
            return response.status_code in [200, 207]
        except Exception as e:
            logger.error(f"Error checking existence of {path}: {e}")
            return False
    
    def read_file(self, path: str) -> Optional[bytes]:
        """读取文件内容"""
        try:
            # 使用正确的路径构建
            url = self._build_url(path)
            logger.info(f"Trying to read file: {url}")
            
            response = self.session.get(url, timeout=30)
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"✓ Successfully read file: {path} ({len(response.content)} bytes)")
                return response.content
            elif response.status_code == 401:
                logger.error(f"✗ Authentication failed (401) for: {path}")
            elif response.status_code == 404:
                logger.error(f"✗ File not found (404): {path}")
            else:
                logger.error(f"✗ Failed with status {response.status_code} for: {path}")
            
            return None
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            return None
    
    def write_file(self, path: str, content: bytes, content_type: str = 'application/octet-stream') -> bool:
        """写入文件"""
        try:
            url = self._build_url(path)
            logger.info(f"Writing file to: {url} ({len(content)} bytes)")
            
            headers = {
                'Content-Type': content_type,
            }
            
            response = self.session.put(url, data=content, headers=headers, timeout=30)
            
            if response.status_code in [200, 201, 204]:
                logger.info(f"Successfully wrote file: {path}")
                return True
            else:
                logger.error(f"Failed to write file {path}: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error writing file {path}: {e}")
            return False
    
    def delete_file(self, path: str) -> bool:
        """删除文件"""
        try:
            url = self._build_url(path)
            logger.info(f"Deleting file: {url}")
            response = self.session.delete(url, timeout=30)
            
            if response.status_code in [200, 204, 404]:
                logger.info(f"Successfully deleted file: {path}")
                return True
            else:
                logger.error(f"Failed to delete file {path}: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file {path}: {e}")
            return False
    
    def create_directory(self, path: str) -> bool:
        """创建目录"""
        try:
            url = self._build_url(path)
            logger.info(f"Creating directory: {url}")
            response = self.session.request('MKCOL', url, timeout=30)
            
            # 200/201: 创建成功
            # 405: 目录已存在（Method Not Allowed）
            # 403: 可能是目录已存在或权限问题
            if response.status_code in [200, 201, 405, 403]:
                if response.status_code == 403:
                    # 403 可能是目录已存在，检查一下
                    if self.exists(path):
                        logger.info(f"Directory already exists: {path}")
                        return True
                    else:
                        logger.error(f"Permission denied when creating directory {path}")
                        return False
                else:
                    logger.info(f"Directory created or already exists: {path}")
                    return True
            else:
                logger.error(f"Failed to create directory {path}: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error creating directory {path}: {e}")
            return False
    
    def list_directory(self, path: str = '') -> List[Dict]:
        """列出目录内容，尝试多个可能的路径前缀"""
        try:
            # 构造多个可能的URL（参照Android应用）
            base_paths = [
                f"{self.base_path}/{path}" if path else self.base_path,
                f"/dav{self.base_path}/{path}" if path else f"/dav{self.base_path}",
                f"/webdav{self.base_path}/{path}" if path else f"/webdav{self.base_path}"
            ]
            
            headers = {'Depth': '1'}
            response = None
            successful_url = None
            
            for base_path in base_paths:
                # 移除开头的斜杠并URL编码
                clean_path = base_path.lstrip('/')
                parts = clean_path.split('/')
                encoded_parts = [quote(part, safe='') for part in parts if part]
                encoded_path = '/'.join(encoded_parts)
                url = f"{self.base_url}/{encoded_path}"
                
                logger.info(f"Trying to list directory: {url}")
                
                response = self.session.request('PROPFIND', url, headers=headers, timeout=30)
                
                if response.status_code in [200, 207]:
                    successful_url = url
                    logger.info(f"✓ Successfully listed directory: {url}")
                    break
                else:
                    logger.info(f"✗ Failed with status {response.status_code}")
            
            if not successful_url or response.status_code not in [200, 207]:
                logger.error(f"Failed to list directory {path} from all attempted paths")
                return []
            
            # 解析 XML 响应
            items = []
            try:
                root = ET.fromstring(response.content)
                namespaces = {
                    'D': 'DAV:',
                    'd': 'DAV:'
                }
                
                for response_elem in root.findall('.//D:response', namespaces) or root.findall('.//d:response', namespaces):
                    href = response_elem.find('.//D:href', namespaces) or response_elem.find('.//d:href', namespaces)
                    if href is not None and href.text:
                        # 获取文件名并URL解码
                        name = unquote(href.text.rstrip('/').split('/')[-1])
                        if name:  # 跳过空名称（当前目录）
                            # 检查是否是目录
                            is_collection = False
                            resourcetype = response_elem.find('.//D:resourcetype', namespaces) or response_elem.find('.//d:resourcetype', namespaces)
                            if resourcetype is not None:
                                collection = resourcetype.find('.//D:collection', namespaces) or resourcetype.find('.//d:collection', namespaces)
                                is_collection = collection is not None
                            
                            items.append({
                                'name': name,
                                'is_directory': is_collection,
                                'path': href.text
                            })
                
                logger.info(f"Found {len(items)} items in directory: {path}")
            except ET.ParseError as e:
                logger.error(f"Failed to parse PROPFIND response: {e}")
            
            return items
        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            return []
    
    def read_json(self, path: str) -> Optional[Dict]:
        """读取 JSON 文件"""
        content = self.read_file(path)
        if content:
            try:
                return json.loads(content.decode('utf-8'))
            except Exception as e:
                logger.error(f"Error parsing JSON from {path}: {e}")
        return None
    
    def write_json(self, path: str, data: Dict) -> bool:
        """写入 JSON 文件"""
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            return self.write_file(path, content, 'application/json; charset=utf-8')
        except Exception as e:
            logger.error(f"Error writing JSON to {path}: {e}")
            return False
    
    def read_csv(self, path: str) -> Optional[str]:
        """读取 CSV 文件"""
        content = self.read_file(path)
        if content:
            try:
                # 移除 BOM
                text = content.decode('utf-8-sig')
                return text
            except Exception as e:
                logger.error(f"Error decoding CSV from {path}: {e}")
        return None
    
    def write_csv(self, path: str, content: str) -> bool:
        """写入 CSV 文件"""
        try:
            # 添加 BOM 以确保 Excel 正确显示中文
            bom = '\ufeff'
            full_content = (bom + content).encode('utf-8')
            return self.write_file(path, full_content, 'text/csv; charset=utf-8')
        except Exception as e:
            logger.error(f"Error writing CSV to {path}: {e}")
            return False
