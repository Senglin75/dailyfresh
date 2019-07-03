from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.contrib.auth import authenticate, login, logout
from django.views.generic import View
from django.conf import settings
from django_redis import get_redis_connection
from django.http import JsonResponse

from utils.mixin import LoginRequiredMixin
from celery_tasks.tasks import send_active_email
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from django.core.paginator import Paginator
import re

from user.models import User, Address
from goods.models import GoodsSKU
from order.models import OrderInfo, OrderGoods


# user/register
class RegisterView(View):
    """注册类"""
    def get(self, request):
        return render(request, 'register.html')

    def post(self, request):
        """注册信息处理"""
        # 1. 接受数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 2. 对数据进行校验

        # 是否接收到数据
        # all 方法,判断参数是否为可迭代对象,
        if not all([username, password, email]):
            return render(request, 'register.html', {'errorMsg': '数据不完整'})

        # 校验邮箱
        if not re.match(r"^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$", email):
            return render(request, 'register.html', {'errorMsg': '邮箱格式错误'})

        # 校验是否同意协议
        if allow != 'on':
            return render(request, 'reigister.html', {'errorMsg': '请同意协议'})

        # 3. 进行业务处理,如用户注册

        # 将注册用户信息放置在数据库中
        # user = User()  # 创建一个 user 对象,通过操作对象的属性或方法,来对数据库进行操作,ORM操作
        # user.username = username
        # user.password = password
        # user.email = email

        # 更新数据库
        # user.save()

        # 校验用户名是否重复
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as e:
            # 用户名不存在
            user = None

        if user:
            return render(request, 'register.html', {'errorMsg': '用户名已存在'})

        # 使用 django 自带的认证系统
        user = User.objects.create_user(username, email, password)
        # 新用户应该是未激活的状态
        user.is_active = 0  # 设置新用户账号未激活
        user.save()

        # 4. 向用户发送激活邮件
        # 5. 使用 itsdangerous 将用户信息加密,防止用户信息泄露
        serializer = Serializer(settings.SECRET_KEY, 3600)  # 选择 django 自带的秘钥生成一个对象,生效时间为 3600s
        info = {'confirm': user.id}
        token = serializer.dumps(info)  # 加密时,加密对象是字典,解密时生成的对象也是字典
        token = token.decode()  # 解密出来的默认为字节形式,解码为 uft-8 格式

        # 发邮件
        send_active_email.delay(email, username, token)  # delay 是任务函数经过装饰后,所拥有的方法
        # 4. 返回应答
        return redirect(reverse('goods:index'))  # reverse 反向解析


# user/active
class ActiveView(View):
    """激活类"""
    def get(self, request, token):
        # 用户点击激活邮箱链接,跳转到 http:127.0.0.1:8000/user/active/token 页面
        serializer = Serializer(settings.SECRET_KEY, 3600)
        try:
            info = serializer.loads(token)
            # 获取激活用户的 id
            user_id = info['confirm']

            # 根据 id 获取用户信息
            user = User.objects.get(id=user_id)
            # 设置用户激活状态为 1,已激活
            user.is_active = 1
            user.save()

            # 跳转到登录界面
            return redirect(reverse('user:login'))  # reverse 里的字典型字符串不能有空格,否则会出现错误
        except SignatureExpired as e:
            # 激活链接已过期,发送一个新的激活邮箱,未完成
            return render(request, 'reActive.html')


# user/login
class LoginView(View):
    """登录"""
    # 登录逻辑
    # 1. 获取数据
    def get(self, request):
        # 判断是否记住用户名
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            # checkbox 元素在接收到 checked 字符串时,会自动将复选框选中
            checked = 'checked'
        else:
            username = ''
            checked = ''
        return render(request, 'login.html', {'username': username, 'checked': checked})

    # 2. 校验数据
    def post(self, request):
        # 检测接受到的数据是否正确
        username = request.POST.get('username')
        password = request.POST.get('pwd')

        if not all([username, password]):
            return render(request, 'login.html', {"errormsg": '数据不完整'})

    # 3. 验证数据
        # 查询数据库中,是否有该用户信息
        user = authenticate(username=username, password=password)
        if user is not None:
            # 已激活
            if user.is_active:
                # 记录用户登录状态,将用户 sesion 存储在 redis 的 cache 里
                login(request, user)

                # 由于 templates 里的 form 表格未设置 action 属性,
                # 因此 form 里的数据会传递到地址栏里
                # LoginRequire 装饰器,会在地址栏后面添加一个 next 参数,用于接收上一次的访问路径
                # 达到在用户在未登录情况下直接访问用户中心,如访问 http://127.0.0.1:8000/user/address 时,跳转到 settings 里设置好的 LOGIN_URL 地址,
                # 并由 next 参数保留先前访问的 user/address 地址,当用户在 user/login 页面登录账号时,立马跳转到 next 参数对应的地址.
                # 未防止用户不是直接访问用户中心,而导致 next 参数接收到的数据为 None,因此设置默认参数,反向解析至首页
                # 获取地址栏的表单数据,地址栏里的数据都是以 GET 方式传递
                next_url = request.GET.get('next', reverse('goods:index'))
                # 跳转到 next_url
                response = redirect(next_url)  # HttpResponseRedirect 对象

                # 判断是否记住用户名
                remeber = request.POST.get('remeber')
                if remeber is not None:
                    # 设置 cookie,保存用户名
                    response.set_cookie('username', username, max_age=7*24*3600)  # max_age 设置 cokie 的过期时间
                else:
                    response.delete_cookie('username')

                # 返回首页
                return response
            else:
                # 未激活
                return render(request, 'login.html', {'errormsg': '用户未激活'})
        else:
            # 用户不存在
            return render(request, 'login.html', {'errormsg': '用户名或密码错误'})


class LogoutView(View):
    """退出登录"""
    def get(self, request):
        # 一旦退出登录,django 会立马清楚当前用户 session 信息
        logout(request)

        # 跳转到主页面
        return redirect(reverse('goods:index'))


# user/
# LoginRequiredMixin 必须在左边,符合方法搜索路径的深度优先遍历算法
class UserView(LoginRequiredMixin, View):
    """用户中心类"""
    def get(self, request):
        page = 'user'
        # django 认证系统会给模板传递一个对象 user
        # 当用户登录时,该对象是 User 的对象
        # 当用户未登录时,该对象是 AnonymousUser 的对象
        # 无论是谁创建出来的对象,都有一个方法--is_authenticated,
        # User.user.is_authenticated 返回的是 True
        # AnonymouseUser.user.is_authenicated 返回的是 False

        # 显示用户信息
        user = request.user

        address = Address.objects.get_default_address(user)

        # 显示用户历史浏览记录

        # 用户浏览记录设计
        # 1. 什么时候产生浏览记录
        # 答: 当用户在浏览商品详情页时,产生浏览记录
        # 2. 什么时候使用浏览记录
        # 答: 当用户浏览个人信息页时,使用浏览记录
        # 3. 使用什么方式存储浏览记录
        # 答: 使用 redis 缓存的方式存储浏览记录,而不是使用 Mysql数据库,防止因操作数据库太频繁,导致数据库压力过大
        # 4. 使用什么类型存储浏览记录
        # 答: 两种思路: 1) 使用 hash 类型, history 当做属性,user_id 当做键值,sku_id 当做值,
        #             2) 使用 list 类型, history_userid 当做键值,sku_id 当做值
        #    由于将所有的浏览记录都存放在一个 hash 列表里,会导致数据冗余、繁杂,不易维护,所以使用 list 的方式为每个用户存储浏览记录

        # 拼凑 redis 里历史浏览记录的键值
        history_userid = 'history_%d' % user.id
        # 获取用户历史浏览记录的前五条记录
        con = get_redis_connection('default')

        sku_ids = con.lrange(history_userid, 0, 4)

        history_goods = []

        # 由于 mysql 数据库在获取数据时,不是按照 id 号存储,只会按存储顺序存储
        # 得将用户最新浏览的几个商品取出

        for sku_id in sku_ids:
            goods = GoodsSKU.objects.get(id=sku_id).order_by('-create_time')
            history_goods.append(goods)

        content = {'page': page,
                   'user': user,
                   'address': address,
                   'history_goods': history_goods,
                   }

        return render(request, 'user_center_info.html', content)


# user/order/page
class OrderView(LoginRequiredMixin, View):
    """用户订单类"""
    def get(self, request, page):
        user = request.user

        # 获取用户所有订单信息
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')

        # 业务处理

        # 遍历用户所有订单,获取单个订单信息
        total_pay = 0
        status = ''
        for order in orders:
            # 获取单个订单里的所有商品信息
            order_skus = OrderGoods.objects.filter(order=order)
            # 动态添加商品小计
            for order_sku in order_skus:
                order_sku.amount = order_sku.price * order_sku.count
                total_pay += order_sku.amount

            # 动态添加单个订单应付金额
            order.total_pay = total_pay + order.transit_price
            # 动态添加单个订单所有商品信息
            order.order_skus = order_skus
            # 动态添加单个订单状态信息,利用字典转化成字符串 '待支付',而不是 1
            order.status = OrderInfo.ORDER_STATUS[str(order.order_status)]
            # 获取单个订单状态信息
            status = order.order_status

        # 设置每页只显示一个订单
        paginator = Paginator(orders, 1)

        # 由于地址栏获取的数据都是字符串形式,当用户输入的 page 是无效值时,默认返回第一页内容
        try:
            page = int(page)
            # num_pages() 返回当前对象的页码总数
            # 当 用户输入的页码超过总页码时,返回第一页内容
            if page > paginator.num_pages:
                page = 1
        except Exception as e:
            page = 1

        # 页码控制,设置显示 5 条页码
        # 1. 当所有页 pages_number < 5 时,显示所有页码
        # 2. 当前页 page 是前三页时,显示 1, page, 3, 4, 5
        # 3. 当前页 page 是最后三页时,显示 page - 2, page -1, page, page + 1, pages_number + 1
        # 4. 其他情况下,显示 page - 2, pgae -1, page, page + 1, page + 2

        # 获取页码总数
        page_numbers = paginator.num_pages

        # 获取当前页订单信息
        order_page = paginator.page(page)

        if page_numbers < 5:
            pages = range(1, page_numbers+1)
        elif page < 3:
            pages = range(1, 6)
        elif page_numbers - page < 2:
            pages = range(page-2, page_numbers+1)
        else:
            pages = range(page-2, page+3)

        # 组织上下文
        context = {'order_page': order_page,
                   'pages': pages,
                   'page': 'order',
                   'status': status}

        return render(request, 'user_center_order.html', context)


# user/address
class AddressView(LoginRequiredMixin, View):
    """用户地址类"""
    def get(self, request):
        page = 'address'

        user = request.user
        # 显示默认地址,如果有默认地址,则后面添加的地址不作为默认地址,否则为默认地址
        address = Address.objects.get_default_address(user)

        return render(request, 'user_center_site.html', {'page': page, 'address': address})

    def post(self, request):
        # 接收数据
        receiver = request.POST.get('receiver')
        add = request.POST.get('add')
        phone = request.POST.get('phone')
        zip_code = request.POST.get('zip_code')

        # 校验数据
        if not all([receiver, add, phone]):
            return render(request, 'user_center_site.html', {'error_msg': '用户数据不完整'})

        if not re.match(r'^1[3|4|5|7|8][0-9]{9}$', phone):
            return render(request, 'user_center_site.html', {'error_msg': '手机号格式不正确'})

        # 业务处理
        # 添加地址

        # 获取用户 User 对象
        user = request.user

        # 在数据库里查询用户 address 信息
        address = Address.objects.get_default_address(user)

        if address:
            is_default = False
        else:
            # 未查到默认地址信息,则将即将设置的地址信息设置为默认地址信息
            is_default = True

        # 添加地址
        Address.objects.create(user=user,
                               receiver=receiver,
                               phone=phone,
                               add=add,
                               zip_code=zip_code,
                               is_default=is_default)

        # 跳转到本页面,显示默认地址
        return redirect(reverse('user:address'))
