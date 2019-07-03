# 使用 celery 来发送邮件,减少用户等待时间
from celery import Celery
from django.core.mail import send_mail
from django.conf import settings
from django.template import loader, RequestContext
from django.shortcuts import render
from goods.models import GoodsType, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner
import os


# 创建一个 celery 实例对象
app = Celery('celery_tasks.tasks', broker='redis://127.0.0.1:6379/3')  # broker 设置中间人,使用 redis 作为中间人


@app.task  # 使用 celery 下的 task 函数对任务函数进行装饰
def send_active_email(to_email, userName, token):
    """设置发送激活邮件任务函数"""
    subject = '天天生鲜激活信息'
    message = ''
    sender = settings.EMAIL_FROM
    receiver = [to_email]
    html_message = '<h1>%s</h1>,<h2>欢迎来到天天生鲜.</h2><br/>请点击以下链接,激活你的账户,<a href="http://127.0.0.1:8000/user/active/%s">http://127.0.0.1:8000/user/active/%s</a>' % (userName, token, token)

    send_mail(subject, message, sender, receiver, html_message=html_message)


@app.task
def generate_static_index():
    """生成首页静态页面"""
    # 总体流程
    # 1. 创建模板文件
    # 2. 保存在 celery 的 worker 电脑上的 static 目录下
    # 3. 在 celery 的 worker 端配置 Nginx,监听 80 端口,配置访问 / 时.返回 static/index.html 文件
    # 4. 当用户访问 127.0.0.1 时,未加端口号,默认访问 80 端口,
    # 5. 完成首页静态页面优化

    # 获取模板
    template = loader.get_template('static_index.html')

    # 组织上下文

    # 获取商品种类信息
    goods_type = GoodsType.objects.all()
    # 获取首页轮播图的信息
    goods_banner = IndexGoodsBanner.objects.all().order_by('index')  # order_by() 根据传来的参数进行排序
    # 获取首页广告的信息
    ad_banner = IndexPromotionBanner.objects.all().order_by('index')

    # 获取首页商品展示信息
    # 通过给 type 添加属性,解决展示区域内既有文字有有图片的问题
    for type in goods_type:
        image_banner = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1)
        title_banner = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0)

        # 动态添加 type 两个属性,防止商品展示区域由于展示的既有图片也有文字而导致模板编写过于复杂
        type.image_banners = image_banner
        type.title_banners = title_banner

    content = {'goods_type': goods_type,
               'goods_banner': goods_banner,
               'ad_banner': ad_banner,
               }

    # 定义上下文
    # 可以直接将变量传给模板文件,不需要 request ,不需要定义上下文
    # context = RequestContext(render(request, content))

    # 渲染模板
    static_index_html = template.render(content)

    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')

    # 将得到的模板文件,写入 static 下的 index.html 文件中
    with open(save_path, 'w') as f:
        f.write(static_index_html)

