from setuptools import setup, find_packages

setup(
    name="moynalog",
    version="0.1.0",
    author="hecurh",
    description="Python клиент для работы с API сервиса Мой налог",
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=[
        "requests",
        "pydantic"
    ],
)