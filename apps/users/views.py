from rest_framework import status  # HTTP 상태코드 모음 (200, 201, 400 등)
from rest_framework.permissions import AllowAny, IsAuthenticated  # 접근 권한 클래스
from rest_framework.request import Request  # 타입 힌트용 Request 클래스
from rest_framework.response import Response  # JSON 응답을 만드는 클래스
from rest_framework.views import APIView  # DRF의 기본 View 클래스
from rest_framework_simplejwt.tokens import RefreshToken  # JWT 토큰 생성 도구

from apps.users.serializers import LoginSerializer, RegisterSerializer, UserSerializer


class RegisterView(APIView):
    permission_classes = [AllowAny]
    # 기본 설정은 "로그인한 사람만 접근 가능"이지만
    # 회원가입은 로그인 전에 하는 것이므로 누구나 접근 가능하도록 변경

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        # request.data: 앱이 보낸 JSON 데이터 (email, password, user_name 등)
        # RegisterSerializer에 데이터를 넘겨서 유효성 검사 준비

        serializer.is_valid(raise_exception=True)
        # 유효성 검사 실행

        user = serializer.save()
        # 검증 통과 후 RegisterSerializer의 create() 메서드 호출 → DB에 유저 저장

        refresh = RefreshToken.for_user(user)
        # 새로 만든 유저의 JWT 토큰 발급
        # refresh: 2주짜리 refresh 토큰
        # refresh.access_token: 1시간짜리 access 토큰

        return Response(
            {
                "user": UserSerializer(user).data,  # 유저 정보 JSON
                "access": str(refresh.access_token),  # 이후 API 요청에 사용할 토큰
                "refresh": str(refresh),  # 토큰 갱신에 사용할 토큰
            },
            status=status.HTTP_201_CREATED,  # 201: 새 리소스가 성공적으로 생성됨
        )


class LoginView(APIView):
    permission_classes = [AllowAny]  # 로그인도 당연히 누구나 접근 가능

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # LoginSerializer의 validate()에서 이메일+비밀번호 확인 후
        # 검증된 user 객체가 validated_data["user"]에 담김

        user = serializer.validated_data["user"]  # 검증된 유저 객체 꺼내기
        refresh = RefreshToken.for_user(user)  # 해당 유저의 JWT 토큰 발급

        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    # 로그인한 사람만 접근 가능 (JWT 토큰 필요)

    def get(self, request: Request) -> Response:
        # request.user: JWT 토큰에서 자동으로 추출한 현재 로그인 유저 객체
        return Response(UserSerializer(request.user).data)
