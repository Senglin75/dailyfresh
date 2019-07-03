from django.conf.urls import url
from user.views import RegisterView, ActiveView, LoginView, UserView, OrderView, AddressView, LogoutView
# from django.contrib.auth.decorators import login_required


urlpatterns = [
    url(r'^register$', RegisterView.as_view(), name='register'),  # 注册
    url(r'^active/(?P<token>.*)$', ActiveView.as_view(), name='avtive'),  # 激活
    url(r'^login', LoginView.as_view(), name='login'),  # 登录
    url(r'^logout', LogoutView.as_view(), name='logout'),  # 注销登录
    # 由于直接使用 login_required(UserView.as_view()) 的方法使得 url 编写起来过于臃肿,
    # 因此单独创建一个类,继承 View 的 as_view 方法,使得 url 编写不变
    # url(r'^user', login_required(UserView.as_view()), name='user'),
    url(r'^user', UserView.as_view(), name='user'),  # 用户信息
    url(r'^address', AddressView.as_view(), name='address'),  # 用户地址
    url(r'^order/(?P<page>\d+)$', OrderView.as_view(), name='order'),  # 用户订单

]