from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.http import JsonResponse
from django.views.generic import View
from django.db import transaction
from django.conf import settings

from goods.models import GoodsSKU
from user.models import Address
from order.models import OrderInfo, OrderGoods
from utils.mixin import LoginRequiredMixin

from django_redis import get_redis_connection
from datetime import datetime
import time
import os
from alipay import AliPay


# order/place
# 获取参数: 用户所购买的商品 id
class OrderPlaceView(LoginRequiredMixin, View):
    """订单提交页面"""
    def post(self, request):
        user = request.user

        # 获取商品 id 列表 ['61', '87', '86]
        sku_ids = request.POST.getlist('sku_ids')

        # 校验商品 id
        if not sku_ids:
            return redirect(reverse('cart:info'))

        # 获取所购商品数量
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        skus = []
        total_price = 0
        total_count = 0
        for sku_id in sku_ids:
            count = conn.hget(cart_key, sku_id)
            # 动态添加商品 count 属性
            sku = GoodsSKU.objects.get(id=sku_id)
            sku.count = int(count)
            # 计算商品小计
            amount = sku.price * sku.count
            # 动态添加商品 amount 属性
            sku.amount = amount
            # 计算商品总金额
            total_price += sku.amount
            # 计算商品总数量
            total_count += sku.count
            skus.append(sku)

        # 获取用户地址
        addrs = Address.objects.filter(user=user)

        # 获取商品运费,一般会单独设计一张表来存储不同规格下的不同运费,这里为了方便,直接设置为 10 元
        freight = 10

        # 计算用户应付金额
        total_pay = total_price + freight

        # 拼接商品 id 字符串,'1,2,3'
        sku_ids = ','.join(sku_ids)

        # 组织上下文
        context = {'skus': skus,
                   'addrs': addrs,
                   'freight': freight,
                   'total_count': total_count,
                   'total_price': total_price,
                   'total_pay': total_pay,
                   'sku_ids': sku_ids}

        return render(request, 'place_order.html', context)


class OrderCommitView(View):
    """
    提交订单
    前后端采用 ajax post 的方式传递数据
    传递参数 sku.id, addr.id, pay_method
    """
    @transaction.atomic
    def post(self, request):
        user = request.user
        # 用户是否登录
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        sku_ids = request.POST.get('sku_ids')
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')

        # 校验参数
        if not all([sku_ids, addr_id, pay_method]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHOD.keys():
            return JsonResponse({'res': 2, 'errmsg': '支付方式不正确'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '地址不正确'})

        # 核心业务: 更新 OrderInfo, OrderGoods 两个表格
        # 由于 OrderInfo 和 OrderGoods 含有外键关系,因此先更新 OrderInfo 表格,再更新 OrderGoods 表格

        # todo: OrderInfo 所需参数: order_id, user, addr, pay_method, total_count, total_price, transit_price

        # 创建订单编号: 创建时间 + user.id
        order_id = datetime.now().strftime('%Y%m%d%H%m%s') + str(user.id)

        total_count = 0
        total_price = 0
        transit_price = 10

        # 设置事务保存点
        save_point = transaction.savepoint()

        try:
            # todo: 向 OrderInfo 表格里添加一条记录

            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=0,
                                             total_price=total_price,
                                             transit_price=transit_price)

            # todo: OrderGoods 所需参数: order, count, price, sku

            # split 将用逗号分开的字符串元素变成列表元素
            sku_ids = sku_ids.split(',')

            # 当多名用户同时下单,导致库存不足时,应取消订单的生成,
            # 引入 事务 的概念,
            # 事务: 要么执行,要么不执行.解决当库存足时,回滚取消订单的生成

            # 当多用户同时下单,如何处理多个订单的生成,
            # 引入 悲观锁,乐观锁 的概念
            # 适用场景: 高并发时

            # 悲观锁
            # 通过给事务上锁的方式来使得多线程在操作数据库时产生的的数据共享的问题得以解决
            # 优点: 强制给事务排序,解决不同事务之间的数据幻读问题(类似数据共享),
            # 缺点: 开启锁需要消耗数据库的资源,并且由于是阻塞式上锁因此需要等待时间
            # 适用场景: 数据库写入较为频繁时

            # 从 redis 里获取订单内商品信息
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            for sku_id in sku_ids:
                try:
                    # 数据库里上锁的语句 select * from df_goods_sku where id = sku_id for update
                    # 给事务上锁 objects.select_for_update().get
                    # 上锁过后,其他事物会阻塞直至事务结束(commit 或 rollback),锁解开
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except GoodsSKU.DoesNotExist:
                    # 撤销数据库操作,并回滚到保存点
                    transaction.savepoint_rollback(save_point)
                    return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                # 获取商品数量
                count = conn.hget(cart_key, sku_id)

                # print('user_id: %d,stock: %d, sku_id: %d' % (user.id, sku.stock, int(sku_id)))
                # time.sleep(5)

                # 判断商品库存
                if int(count) > sku.stock or sku.stock < 0:
                    # 撤销数据库操作,并回滚到保存点
                    transaction.savepoint_rollback(save_point)
                    return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})

                # 更新商品库存和销量
                sku.stock -= int(count)
                sku.sales += int(count)
                # 对数据库操作之后,切记一定要保存,否则之前对数据库的操作无效!!!
                sku.save()

                # 获取商品小计
                amount = sku.price * int(count)
                # 计算商品总数量
                total_count += int(count)
                # 计算商品总价
                total_price += amount

                # todo: 向 OrderGoods 表格里添加数据
                order_goods = OrderGoods.objects.create(order=order,
                                                        sku=sku,
                                                        count=count,
                                                        price=sku.price)
                # 更新 OrderGoods 数据库
                order_goods.save()
                # print('after update sql, stock: %d' % sku.stock)

            # 删除 redis 购物车里的记录
            conn.delete(cart_key, *sku_ids)  # *sku_ids(*[1, 2]) * 是拆包操作符,将列表里的元素拿出来逐个操作

            # 更新 OrderInfo 里 total_count 和total_price 的信息
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            # 当涉及到数据库操作时,出现错误,则撤销此次数据库操作,回滚到设置的保存点之前
            transaction.savepoint_rollback(save_point)

        # 订单提交成功
        # 数据库操作成功,提交事务
        transaction.savepoint_commit(save_point)

        return JsonResponse({'res': 5, 'errmsg': '订单提交成功'})


class OrderCommitView01(View):
    """
    提交订单
    前后端采用 ajax post 的方式传递数据
    传递参数 sku.id, addr.id, pay_method
    """
    @transaction.atomic
    def post(self, request):
        user = request.user
        # 用户是否登录
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        sku_ids = request.POST.get('sku_ids')
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')

        # 校验参数
        if not all([sku_ids, addr_id, pay_method]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHOD.keys():
            return JsonResponse({'res': 2, 'errmsg': '支付方式不正确'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '地址不正确'})

        # 核心业务: 更新 OrderInfo, OrderGoods 两个表格
        # 由于 OrderInfo 和 OrderGoods 含有外键关系,因此先更新 OrderInfo 表格,再更新 OrderGoods 表格

        # todo: OrderInfo 所需参数: order_id, user, addr, pay_method, total_count, total_price, transit_price

        # 创建订单编号: 创建时间 + user.id
        order_id = datetime.now().strftime('%Y%m%d%H%m%s') + str(user.id)

        total_count = 0
        total_price = 0
        transit_price = 10

        # 设置事务保存点
        save_point = transaction.savepoint()

        try:
            # todo: 向 OrderInfo 表格里添加一条记录

            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=0,
                                             total_price=total_price,
                                             transit_price=transit_price)

            # todo: OrderGoods 所需参数: order, count, price, sku

            # split 将用逗号分开的字符串元素变成列表元素
            sku_ids = sku_ids.split(',')

            # 乐观锁
            # 通过给数据库添加一个版本号 version,每当一个事务完成后,版本号 + 1,
            # 当不同事务执行时,比较当前版本号与上一个版本号是否一致,
            # 如果版本号不一致,则认为当前数据已被修改,那么通知用户重新执行事务,一般最多重复执行三次.

            # 由于 mysql 默认事务隔离级别为 Repeatable Read,
            # 使得在乐观锁情况下,多个事务之间出现幻读(类似数据共享),
            # 引发当一个事务在处理一条数据时,另个事务同时修改数据,导致前一个事务可以看到修改后的数据,也就是幻读.

            # 解决方法: 设置 mysql 默认的事务隔离级别为 Read Committed,
            # 找到 /etc/mysql/mysql.conf.d/mysqld.cnf,添加 transaction-isolation = READ-COMMITTED
            # 使得事务只能读取到已经提交的数据,防止多个事务之间的数据共享问题,这里也是事务隔离性的体现.

            # 优点: 不涉及到锁,节省资源,不同事务之间没有等待时间,提高了系统的效率.
            # 缺点: 如果在一个事务执行期间,另一个事务对数据库同时进行了写入操作,会出现幻读现象.
            # 适用场景: 数据库读取较为频繁时

            # 从 redis 里获取订单内商品信息
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            for sku_id in sku_ids:
                for i in range(3):
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except GoodsSKU.DoesNotExist:
                        # 撤销数据库操作,并回滚到保存点
                        transaction.savepoint_rollback(save_point)
                        return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                    # 获取商品数量
                    count = conn.hget(cart_key, sku_id)

                    # 判断库存是否不足
                    if int(count) > sku.stock or sku.stock < 0:
                        transaction.savepoint_rollback(save_point)
                        return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})

                    # todo: 更新商品库存和销量,(设置版本号)

                    # 更新前的库存和销量
                    origin_stock = sku.stock
                    origin_sales = sku.sales

                    # 更新后的库存和销量
                    new_stock = origin_stock - int(count)
                    new_sales = origin_sales + int(count)

                    time.sleep(5)
                    print('user_id: %d, stock :%d, times: %d' % (user.id, sku.stock, i))

                    # 判断商品库存,如果当前库存跟更新前的库存数不一致,说明数据被改动 ,则尝试重新更新数据库
                    # 更新 sql 语句:
                    # update df_goods_sku set stock=new_stock, set sales=new_sales
                    # where id = sku_id and stock = origin_stock
                    # res 是受影响行数, 1 表示成功更新数据库一条数据, 0 表示失败

                    res = GoodsSKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=new_stock, sales=new_sales)
                    # print('res: %d' % res)

                    if res == 0:
                        # 数据库更新失败
                        if i == 2:
                            # 尝试更新 3 次后,仍然失败,则事务回滚
                            transaction.savepoint_rollback(save_point)
                            return JsonResponse({'res': 7, 'errmsg': '尝试失败'})
                        # 事务尝试更新数据库三次
                        continue

                    # 获取商品小计
                    amount = sku.price * int(count)
                    # 计算商品总数量
                    total_count += int(count)
                    # 计算商品总价
                    total_price += amount

                    # todo: 更新 OrderGoods 表
                    order_goods = OrderGoods.objects.create(order=order,
                                                            sku=sku,
                                                            count=count,
                                                            price=sku.price)
                    # 更新 OrderGoods 表
                    order_goods.save()

                    # 事务更新数据成功,退出循环
                    break

                # 更新 OrderInfo 里 total_count 和total_price 的信息
                order.total_count = total_count
                order.total_price = total_price
                order.save()

                # 删除 redis 购物车里的记录
                conn.delete(cart_key, *sku_ids)  # *sku_ids(*[1, 2]) * 是拆包操作符,将列表里的元素拿出来逐个操作

        except Exception as e:
            # 当涉及到数据库操作时,出现错误,则撤销此次数据库操作,回滚到设置的保存点之前
            transaction.savepoint_rollback(save_point)

        # 订单提交成功
        # 数据库操作成功,提交事务
        transaction.savepoint_commit(save_point)

        return JsonResponse({'res': 5, 'errmsg': '订单提交成功'})


# order/pay
# ajax post
# 传递参数: order_id
class OrderPayView(View):
    """
    订单支付
    使用支付宝接口,创建电脑支付,
    django 网站想 alipay 发送支付请求,
    传递参数: 订单编号(order_id), 应付金额(total_pay), 订单主题(subject),
    调用接口 alipay.trade.page.pay
    python-alipay-sdk 的接口封装成 api_alipay_trade_page_pay
    """
    def post(self, request):
        user = request.user

        print('begin')
        # 校验参数
        if not user.is_authenticated():
            return redirect(reverse('user:login'))

        order_id = request.POST.get('order_id')

        if not order_id:
            return JsonResponse({'res': 0, 'errmsg': '数据不正确'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)

        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 1, 'errmsg': '订单无效'})

        app_private_key_string=open(os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem')).read()
        alipay_public_key_string = open(os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem')).read()

        alipay = AliPay(
            appid='2016101100657939',
            app_notify_url=None,  # 默认回调url
            app_private_key_string=app_private_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",  # RSA 或者 RSA2,推荐使用 RSA2
            debug=True  # 默认False,访问真实环境,改为 True,访问沙箱环境
        )

        subject = "天天生鲜%d" % user.id

        total_pay = order.transit_price + order.total_price

        # 电脑网站支付，需要跳转到https://openapi.alipay.com/gateway.do? + order_string

        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order.order_id,
            total_amount=str(total_pay),  # 由于 alipay 会将数据转换为 json 格式,而 total_pay 是 Decimal 格式,不支持转化为 json,因此将它格式化为字符串
            subject=subject,
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )

        # 沙箱环境的 url 为 alipaydev
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string

        # 返回应答
        return JsonResponse({'res': 2, 'pay_url': pay_url, 'errmsg': '跳转 alipay 支付界面'})


# order/check
# ajax post
# 传递参数: order_id
class OrderCheckView(View):
    """
    检查支付结果
    由于 alipay 支付结果会直接与用户交互,而不是与 django 网站进行交互,
    因此需要 django 网站自己向 alipay 发送订单支付结果查询,
    又因为 django 网站不会主动向用户发送请求,因此在用户点击 '去付款' 后,前端页面紧接着向 django 服务器发送 ajax post 请求,
    django 网站会向 alipay 请求询问订单支付结果.
    传递参数: order_id
    使用接口 alipay.trade.query
    sdk 接口为 api_alipay_trade_query
    """
    def post(self, request):
        user = request.user

        # 校验参数
        if not user.is_authenticated():
            return redirect(reverse('user:login'))

        order_id = request.POST.get('order_id')

        if not order_id:
            return JsonResponse({'res': 0, 'errmsg': '数据不正确'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          )
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 1, 'errmsg': '订单无效'})

        # alipay_public_key 获取 alipay 的公钥 用来对 ailpay 发来的数据进行解密
        # app_private_key 获取用户的私钥,用来对用户向 alipay 发送的数据进行加密
        app_private_key_string = open(os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem')).read()
        alipay_public_key_string = open(os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem')).read()

        alipay = AliPay(
            appid='2016101100657939',
            app_notify_url=None,  # 默认回调url
            app_private_key_string=app_private_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",  # RSA 或者 RSA2,推荐使用 RSA2
            debug=True  # 默认False,访问真实环境,改为 True,访问沙箱环境
        )

        # """
        # response = {
        #   "alipay_trade_query_response": {
        #     "trade_no": "2017032121001004070200176844",  # 交易号
        #     "code": "10000",  # 支付结果的网关码,用来反映支付接口的调用情况和业务代码执行情况
        #     "invoice_amount": "20.00",
        #     "open_id": "20880072506750308812798160715407",
        #     "fund_bill_list": [
        #       {
        #         "amount": "20.00",
        #         "fund_channel": "ALIPAYACCOUNT"
        #       }
        #     ],
        #     "buyer_logon_id": "csq***@sandbox.com",
        #     "send_pay_date": "2017-03-21 13:29:17",
        #     "receipt_amount": "20.00",
        #     "out_trade_no": "out_trade_no15",
        #     "buyer_pay_amount": "20.00",
        #     "buyer_user_id": "2088102169481075",
        #     "msg": "Success",
        #     "point_amount": "0.00",
        #     "trade_status": "TRADE_SUCCESS",  # 支付结果
        #     "total_amount": "20.00"
        #   },
        #   "sign": ""
        # }
        # """

        # todo: 根据 response 来执行相关业务

        # 设置等待时间,超过一分钟,则认为用户不在支付
        timeout = 60
        while True:
            # 调用接口, django 网站向 alipay 询问订单交易情况
            response = alipay.api_alipay_trade_query(out_trade_no=order_id)  # out_trade_no 订单编号

            # 获取支付网关码
            # 10000 接口调用成功
            # 20000 服务不可用,稍后重试
            # 40004 接口调用成功,但是业务代码处理失败,稍后重试
            # 还有其他网关码
            # 支付成功
            code = response.get('code')
            print(code)

            # 获取支付状态
            status = response.get('trade_status')
            print(status)

            # 支付成功
            if code == '10000' and status == 'TRADE_SUCCESS':
                # 执行业务代码
                # 更新订单状态为待评价
                order.order_status = 4
                order.trade_no = response.get('trade_no')
                order.save()
                return JsonResponse({'res': 2, 'message': '支付成功'})

            # 两种稍后重试的情况
            # 1. 接口调用成功,但是用户未付款
            # 2. 接口调用成功,但是业务处理失败,等待 1 分钟后,断开连接
            elif code == '10000' and status == 'WAIT_BUYER_PAY':
                # 延时几秒钟,等待用户支付
                time.sleep(5)
                continue

            # 调用接口过长,自动断开连接
            elif code == '40004':
                while timeout < 0:
                    return JsonResponse({'res': 3, 'errmsg': '等待时间过长'})
                time.sleep(1)
                timeout -= 1
                continue

            # 支付失败
            else:
                return JsonResponse({'res': 4, 'errmsg': '支付失败'})


class OrderCommentView(LoginRequiredMixin, View):
    """
    订单评论页面

    两种情况: 1. 用户添加评论
             2. 详情页评论展示

    1. 跳转至 order/comment 页面,
       传递参数: order
    """

    def get(self, request, order_id):
        """显示用户订单评论页"""
        user = request.user

        # 校验参数
        if not user.is_authenticated():
            return redirect(reverse('user:login'))

        if not order_id:
            return redirect(reverse('user:order'))

        try:
            # get 和 filter 的区别:
            #   get: 返回的结果有且只有一个,因此条件必须是唯一不可混淆的,
            #   filter: 返回的是一个 QuerySet 格式的结果集,可以遍历,可以循环,但是不能等同于 list
            # 当 get 取得多个结果或未取得结果时,会直接报错,导致代码停止运行
            # 而 filter 就算未取得结果时,也不会报错
            # 使用场景:
            #   当明确知道要取得的结果且结果只有一个时,使用 get
            #   当不是很明确结果时,使用 filter
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user)

        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:order', kwargs={'page': 1}))

        # 获取订单里的商品
        order_skus = OrderGoods.objects.filter(order=order)

        # 遍历订单商品,动态添加小计
        for order_sku in order_skus:
            # 单个商品动态添加小计
            order_sku.total_amount = order_sku.price * order_sku.count

        # 单个订单动态添加商品
        order.order_skus = order_skus
        # 单个订单动态添加订单状态
        order.status_name = OrderInfo.ORDER_STATUS[str(order.order_status)]

        # 返回应答
        return render(request, 'order_comment.html', {'order': order})

    def post(self, request, order_id):
        """提交评论内容"""

        user = request.user

        print(order_id)

        # 校验参数
        if not user.is_authenticated():
            return redirect(reverse('user:login'))

        if not order_id:
            return redirect(reverse('user:order', kwargs={'page': 1}))

        try:
            # get 和 filter 的区别:
            #   get: 返回的结果有且只有一个,因此条件必须是唯一不可混淆的,
            #   filter: 返回的是一个 QuerySet 格式的结果集,可以遍历,可以循环,但是不能等同于 list
            # 当 get 取得多个结果或未取得结果时,会直接报错,导致代码停止运行
            # 而 filter 就算未取得结果时,也不会报错
            # 使用场景:
            #   当明确知道要取得的结果且结果只有一个时,使用 get
            #   当不是很明确结果时,使用 filter
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user)

        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:order'))

        # 获取订单所有商品的评论数目
        count = int(request.POST.get('total_count'))

        # 遍历所有评论,为每个商品更新评论
        for i in range(1, count+1):
            # 获取商品信息
            sku_id = request.POST.get('sku_%d' % i)
            sku = GoodsSKU.objects.get(id=sku_id)
            # 获取商品评论
            content = request.POST.get('content_%d' % i)

            # 为商品更新评论
            try:
                order_sku = OrderGoods.objects.get(order=order, sku=sku)
            except Exception as e:
                continue

            print(content)

            order_sku.comment = content
            # 更新商品,订单状态
            order.order_status = 5
            order_sku.save()
            order.save()

        # 返回应答
        return redirect(reverse('user:order', kwargs={'page': 1}))











