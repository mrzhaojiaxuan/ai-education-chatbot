import os
import subprocess
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 加载环境变量配置文件
load_dotenv()

# 从环境变量中读取数据库配置信息
db_host = os.getenv("DB_HOST", "localhost")
db_port = os.getenv("DB_PORT", "3306")
db_name = os.getenv("DB_NAME", "ecs")
db_user_name = os.getenv("DB_USER", "root")
db_password = os.getenv("DB_PASSWORD", "root")

# 构建数据库连接 URL
url = f"mysql+pymysql://{db_user_name}:{db_password}@{db_host}:{db_port}/{db_name}?charset=utf8"

# 创建数据库引擎
engine = create_engine(url)

# 配置会话工厂，绑定到数据库引擎
# autocommit=False: 关闭自动提交，需要手动调用 commit()
# autoflush=False: 关闭自动刷新，避免不必要的数据库查询
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

if __name__ == "__main__":

    def export_db_table_class(run=False):
        """
        将数据库表映射为Python类，使用 sqlacodegen 工具自动生成
        :param run: 是否执行导出操作，默认为 False
        """
        if not run:
            return
        output_path = "db_table_class.py"

        # 构建 sqlacodegen 命令，从数据库生成 ORM 类
        cmd = ["python", "-m", "sqlacodegen", url]
        # 执行命令并捕获输出
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        # 将生成的代码写入文件
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.stdout)

    # 执行数据库表导出操作，生成 db_table_class.py 文件
    export_db_table_class(True)