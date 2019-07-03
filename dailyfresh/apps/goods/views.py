from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.core.cache import cache
from django.core.paginator import Paginator
from django_redis import get_redis_connection
from django.http import HttpResponse
from goods.models import GoodsType, GoodsSKU, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner
from order.models import OrderGoods


# Create your views here.
class IndexView(View):
    """首页"""
    def get(self, request):
        # 先读取缓存,如果缓存为空,则设置缓存
        content = cache.get('index_cache_data')

        if content is None:
            # 获取商品种类信息
            goods_types = GoodsType.objects.all()
            # 获取首页轮播图的信息
            goods_banner = IndexGoodsBanner.objects.all().order_by('index')  # order_by() 根据传来的参数进行排序
            # 获取首页广告的信息
            ad_banner = IndexPromotionBanner.objects.all().order_by('index')

            # 获取首页商品展示信息
            # 通过给 type 添加属性,解决展示区域内既有文字有有图片的问题
            for type in goods_types:
                image_banner = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1)
                title_banner = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0)

                # 动态添加 type 两个属性,防止商品展示区域由于展示的既有图片也有文字而导致模板编写过于复杂
                type.image_banners = image_banner
                type.title_banners = title_banner

            # 组织上下文
            content = {'goods_types': goods_types,
                       'goods_banner': goods_banner,
                       'ad_banner': ad_banner,
                       }

            # 设置缓存,减少对数据库的操作频率,提高用户的访问速度,一定程度上提高抵御 DDOS 攻击的能力
            # cache.set(key, value, timeout)
            cache.set('index_cache_data', content, 3600)

        # 购物车信息
        user = request.user

        # 用户登录状态下,获取 redis 里的购物车记录,购物车记录使用 hash 方式存储, cart_userid 用作 hash 的键,商品 sku 用作属性,商品的数量用作值
        cart_count = 0
        if user.is_authenticated():
            conn = get_redis_connection('default')
            curt_hkey = 'cart_%d' % user.id
            cart_count = conn.hlen(curt_hkey)  # hash 里的 hlen 方法,可以获取到当前键下的所有值的总数

        content.update({'cart_count': cart_count})

        return render(request, 'index.html', content)


# /goods/detail/goods_id
class DetailView(View):
    """商品详情页"""
    def get(self, request, goods_id):
        # 获取商品种类: GoodsType
        # 获取商品信息: GoodsSKU,Goods
        # 获取商品订单信息: OrderGoods
        # 获取购物车信息: User

        # 获取商品种类
        goods_types = GoodsType.objects.all()

        # 获取商品信息
        try:
            # 尝试获取用户要访问的 goods,防止用户输入 goods_id 是个无效值
            sku = GoodsSKU.objects.get(id=goods_id)
        except GoodsSKU.DoesNotExist:
            # 当用户访问的商品不存在时,使其返回首页
            return redirect(reverse('goods:index'))

        # 获取商品的所有订单信息中的评论
        orders = OrderGoods.objects.filter(sku=sku)

        # 获取新品推荐信息,每次只显示两个新品,由创建时间来确定是否是新品
        new_goods_recommend = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time').exclude(id=goods_id)[:2]  # exclude 返回不包括传入参数的内容,order_by('-count') 按照 count 倒叙的方式排列

        # 同一 SPU 下的其他规格商品
        same_spu_skus = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=goods_id)

        # 组织上下文
        context = {'goods_types': goods_types,
                   'sku': sku,
                   'orders': orders,
                   'new_goods_recommend': new_goods_recommend,
                   'same_spu_skus': same_spu_skus,
                   }

        # 获取购物车信息
        user = request.user

        # 用户登录状态下,获取 redis 里的购物车条目数量,
        # 购物车记录使用 hash 方式存储, cart_userid 用作 hash 的键,商品 sku 用作属性,商品的数量用作值
        cart_count = 0
        if user.is_authenticated():
            conn = get_redis_connection('default')
            curt_hkey = 'cart_%d' % user.id
            cart_count = conn.hlen(curt_hkey)  # hash 里的 hlen 方法,可以获取到当前键下的所有属性的总数

            # 添加历史浏览记录,
            history_key = 'history_%d' % user.id

            # 由于用户可能会前后两次点击同一件商品,导致 redis 里产生冗余数据,因此先尝试删除 redis 里所有本次用户所点击商品的记录,再将本次浏览记录添加进去
            # conn.lrem(key, count, value)
            # count 为 0 时,删除所有 list 里的 value 值,> 0 时,从左往右删除 count 个 value, < 0 时,从右往左删除 count 个 value
            # 没有 value 时,无操作
            conn.lrem(history_key, 0, sku.id)

            # 从左往右添加历史浏览记录
            conn.lpush(history_key, sku.id)

        context.update({'cart_count': cart_count})

        return render(request, 'detail.html', context)


# /list/type_id,不合适
# /list/type_id/page/?sort=  设计地址栏 url 为 /list/商品类型/当前页码/排序方式,其中 sort 通过 GET 方式获取
class ListView(View):
    """商品列表页"""
    def get(self, request, type_id, page):
        # 获取用户输入的商品种类
        try:
            types = GoodsType.objects.get(id=type_id)
        except GoodsType.DoesNotExist:
            return redirect(reverse('goods:index'))

        # 获取所有商品种类
        goods_types = GoodsType.objects.all()

        # 获取商品新品推荐
        new_goods_commend = GoodsSKU.objects.filter(type=types).order_by('-create_time')[:2]

        # 获取一个种类下的所有商品信息,并将商品根据地址栏获取的排序方式进行排序
        sort = request.GET.get('sort')
        # 三种排序方式,default,price,sales
        if sort == 'price':
            goods_list = GoodsSKU.objects.filter(type=types).order_by('price')
        elif sort == 'sales':
            goods_list = GoodsSKU.objects.filter(type=types).order_by('-sales')
        else:
            sort = 'default'
            goods_list = GoodsSKU.objects.filter(type=types).order_by('-id')

        # 将所有商品按一页一个商品的方式分页
        paginator = Paginator(goods_list, 1)

        # 由于地址栏获取的数据都是字符串形式,当用户输入的 page 是无效值时,默认返回第一页内容
        try:
            page = int(page)
            # num_pages() 返回当前对象的页码总数
            # 当 用户输入的页码超过总页码时,返回第一页内容
            if page > paginator.num_pages:
                page = 1
        except Exception as e:
            page = 1

        # 获取当前页码下的商品
        goods_page = paginator.page(page)

        # 页码控制,设置显示 5 条页码
        # 1. 当所有页 pages_number < 5 时,显示所有页码
        # 2. 当前页 page 是前三页时,显示 1, page, 3, 4, 5
        # 3. 当前页 page 是最后三页时,显示 page - 2, page -1, page, page + 1, pages_number + 1
        # 4. 其他情况下,显示 page - 2, pgae -1, page, page + 1, page + 2

        # 获取页码总数
        page_numbers = paginator.num_pages

        if page_numbers < 5:
            pages = range(1, page_numbers+1)
        elif page < 3:
            pages = range(1, 6)
        elif page_numbers - page < 2:
            pages = range(page-2, page_numbers+1)
        else:
            pages = range(page-2, page+3)

        # 获取购物车信息
        user = request.user

        cart_count = 0
        if user.is_authenticated():
            # 用户登录状态下,获取用户购物车商品数量
            curt_hkey = 'curt_%d' % user.id
            conn = get_redis_connection('default')
            cart_count = conn.hlen(curt_hkey)

        # 组织上下文
        context = {'goods_types': goods_types,
                   'types': types,
                   'new_goods_commend': new_goods_commend,
                   'goods_page': goods_page,
                   'sort': sort,
                   'pages': pages,
                   'cart_count': cart_count}

        return render(request, 'list.html', context)





