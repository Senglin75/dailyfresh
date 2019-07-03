from django.core.files.storage import Storage
from django.conf import settings
from fdfs_client.client import Fdfs_client


class FDFSStorage(Storage):
    """修改 Django 默认的文件存储类,创建一个 fastDFS 的文件存储类"""
    def __init__(self, client_conf=None, base_path=None):
        if client_conf is None:
            client_conf = settings.CLIENT_CONF
        self.client_conf = client_conf

        if base_path is None:
            base_path = settings.FDFS_PATH
        self.base_path = base_path

    def exists(self, name):
        # Django 在调用 save 之前会先判断该文件是否已经在 Django 中存储了,
        # 由于不使用 Django 默认的存储方式,所以一直返回 False,该文件不存在 Django 中
        return False

    def _open(self, name, mode='rb'):
        # 从 Django 中下载文件时,使用该方法,与图片上传无关
        pass

    def _save(self, name, content):
        # 向 Django 中上传文件时,使用该方法,如 图片上传
        # name 是上传的文件名字
        # content 是上传的 File 对象

        # 创建一个 Fdfs_cilent 对象,使得 fastdfs 与 Python 交互
        client = Fdfs_client(self.client_conf)

        # 上传文件当 fastdfs 文件系统中
        # upload_by_buffer 通过文件内容的方式上传
        # content 是包含上传文件内容的 File 对象,其方法 read() 可以读取上传的文件内容
        res = client.upload_by_buffer(content.read())

        # 返回的是一个字典
        # dict
        # {
        #     'Group name': group_name,
        #     'Remote file_id': remote_file_id,
        #     'Status': 'Upload successed.',
        #     'Local file name': '',
        #     'Uploaded size': upload_size,
        #     'Storage IP': storage_ip
        # }

        if res.get('Status') != 'Upload successed.':
            raise Exception('上传文件失败')
        file_id = res.get('Remote file_id')

        return file_id

    def url(self, name):
        """返回文件存储后的文件 url,即 ImageFile 字段的 image 的 url 属性值,
        image 的 url 默认格式是 ImageFile 的 upload_to 属性值/文件名',
        修改过后,为 nginx 的域名:端口号/image.url"""
        return self.base_path + name



