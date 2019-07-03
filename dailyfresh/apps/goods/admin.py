from django.contrib import admin
from celery_tasks.tasks import generate_static_index
from django.core.cache import cache
from goods.models import GoodsSKU, Goods, GoodsType, IndexTypeGoodsBanner, IndexGoodsBanner, IndexPromotionBanner


class BaseModelAdmin(admin.ModelAdmin):
    """当管理员在后台将首页数据更改后,Nginx 上应生成一个新的 index.html"""
    def save_model(self, request, obj, form, change):
        # 执行 admin.ModelAdmin 里的 save_model 方法,修改数据
        super().save_model(request, obj, form, change)

        # 修改完之后,发出任务,在 Nginx 上重新生成 index.html
        # 使用 celery 异步生成 index.html,可以防止管理员在后台等待刷新

        generate_static_index.delay()

        # 更改之后,删除缓存,防止用户访问的一直是之前缓存过的内容,而不是新的内容
        cache.delete('index_cache_data')

    def delete_model(self, request, obj):
        # 删除数据
        # 由于 admin 管理界面,存在这批量删除操作,因此 delete_model 函数是不会被调用的,而是会调用性能更加高的 query_set() 函数,
        super().delete_model(request, obj)

        generate_static_index.delay()

        cache.delete('sindex_cache_data')


class GoodsTypeAdmin(BaseModelAdmin):
    pass


class IndexPromotionBannerAdmin(BaseModelAdmin):
    pass


class IndexTypeGoodsBannerAdmin(BaseModelAdmin):
    pass


class IndexGoodsBannerAdmin(BaseModelAdmin):
    pass


class GoodsSKUAdmin(BaseModelAdmin):
    pass


class GoodsAdmin(BaseModelAdmin):
    pass


admin.site.register(GoodsType, GoodsTypeAdmin)
admin.site.register(IndexTypeGoodsBanner, IndexTypeGoodsBannerAdmin)
admin.site.register(IndexGoodsBanner, IndexGoodsBannerAdmin)
admin.site.register(IndexPromotionBanner, IndexPromotionBannerAdmin)
admin.site.register(GoodsSKU, GoodsSKUAdmin)
admin.site.register(Goods, GoodsAdmin)


