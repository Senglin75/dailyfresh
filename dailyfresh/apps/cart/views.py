from django.shortcuts import render
from django.views.generic import View
from django.http.response import JsonResponse
from django_redis import get_redis_connection
from django.core.urlresolvers import reverse
from django.shortcuts import render

from goods.models import GoodsSKU
from utils.mixin import LoginRequiredMixin


# /cart/add
class AddCartView(View):
    """
    购物车添加页面

    前端传递数据: sku_id, count
    前后端交互方式: ajax,一种不提交地址栏,且只会在后台发生变化的方式
    """
    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '未登录'})

        # 接收数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验数据
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 检验 count 是否合法
        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目不合法'})

        # 检验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 业务处理,添加购物车
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 向 redis 里设置购物车记录
        # 如果 redis 里有该商品的记录,则对其数目进行累加,否则添加新的记录
        num = conn.hget(cart_key, sku.id)
        if num:
            # 由于 redis 里存储的都是 str 数据,因此需要转化成 int
            count += int(num)

        # hset 有则更新,无则添加
        conn.hset(cart_key, sku.id, count)
        # 返回购物车里所有条目数
        count = int(conn.hlen(cart_key))
        # 返回应答
        return JsonResponse({'res': 4, 'errmsg': '添加成功', 'count': count})


# /cart
class CartInfoView(LoginRequiredMixin, View):
    """购物车内容展示页面"""
    def get(self, request):
        # 获取所有购物车商品数量
        user = request.user
        cart_key = 'cart_%d' % user.id
        conn = get_redis_connection('default')

        # 获取商品信息
        goods_list = []
        total_acount = 0
        total_count = 0
        for sku_id, count in conn.hgetall(cart_key).items():
            # 动态添加商品数量
            sku = GoodsSKU.objects.get(id=sku_id)
            sku.count = int(count)
            # 动态添加商品小计
            sku.cost = sku.count * sku.price
            goods_list.append(sku)
            # 计算商品总价,总数目
            total_acount += sku.cost
            total_count += sku.count

        context = {'goods_list': goods_list,
                   'total_acount': total_acount,
                   'total_count': total_count}

        return render(request, 'cart.html', context)


# /cart/update
class UpdateCartView(View):
    """
    购物车页面更新
    采用 ajax post 方式,
    传递 sku_id,count 数据
    """

    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '未登录'})

        # 接收数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验数据
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 检验 count 是否合法
        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目不合法'})

        # 检验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 业务处理,redis 购物车商品数量更新
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 更新 redis 的商品的数量
        conn.hset(cart_key, sku_id, count)

        # 将更新后的商品数量传递给模板
        vals = conn.hvals(cart_key)

        total_count = 0
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 4, 'total_count': total_count, 'errmsg': '更新成功'})


# /cart/delete
class DeleteCartView(View):
    """
    删除购物车记录
    请求方式: ajax post
    请求数据 sku_id
    """
    # 判断用户是否登录
    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '未登录'})

        # 接收数据
        sku_id = request.POST.get('sku_id')

        # 校验数据
        if not all([sku_id]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 检验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 业务处理
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 删除 redis 里的购物车记录
        conn.hdel(cart_key, sku_id)

        # 返回更新后的购物车总数目

        total_count = 0

        for val in conn.hvals(cart_key):
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 3, 'total_count': total_count, 'errmsg': '商品删除成功'})
