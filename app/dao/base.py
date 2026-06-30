from sqlalchemy.future import select
from sqlalchemy import update as sqlalchemy_update, delete as sqlalchemy_delete, func
from app.database import async_session_maker


class BaseDAO:
    model = None  # Устанавливается в дочернем классе

    @classmethod
    async def find_one_or_none_by_id(cls, data_id: int):
        # Найти запись по ID
        async with async_session_maker() as session:
            query = select(cls.model).filter_by(id=data_id) # type: ignore
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def find_one_or_none(cls, **filter_by):
        # Найти одну запись по фильтрам
        async with async_session_maker() as session:
            query = select(cls.model).filter_by(**filter_by) # type: ignore
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def find_all(cls, **filter_by):
        # Найти все записи по фильтрам
        async with async_session_maker() as session:
            query = select(cls.model).filter_by(**filter_by) # type: ignore
            result = await session.execute(query)
            return result.scalars().all()

    @classmethod
    async def add(cls, **values):
        # Добавить одну запись
        async with async_session_maker() as session:
            async with session.begin():
                new_instance = cls.model(**values) # type: ignore
                session.add(new_instance)
                await session.flush()
                await session.refresh(new_instance)
                return new_instance

    @classmethod
    async def add_many(cls, instances: list[dict]):
        # Добавить несколько записей
        async with async_session_maker() as session:
            async with session.begin():
                new_instances = [cls.model(**values) for values in instances] # type: ignore
                session.add_all(new_instances)
                await session.flush()
                for instance in new_instances:
                    await session.refresh(instance)
                return new_instances

    @classmethod
    async def update(cls, filter_by, **values):
        # Обновить записи по фильтру
        async with async_session_maker() as session:
            async with session.begin():
                query = (
                    sqlalchemy_update(cls.model) # type: ignore
                    .where(*[getattr(cls.model, k) == v for k, v in filter_by.items()])
                    .values(**values)
                    .execution_options(synchronize_session="fetch")
                )
                result = await session.execute(query)
                return result.rowcount # type: ignore

    @classmethod
    async def delete(cls, delete_all: bool = False, **filter_by):
        # Удалить записи по фильтру
        if not delete_all and not filter_by:
            raise ValueError("Нужен хотя бы один фильтр для удаления.")

        async with async_session_maker() as session:
            async with session.begin():
                query = sqlalchemy_delete(cls.model) # type: ignore
                if not delete_all:
                    query = query.where(*[getattr(cls.model, k) == v for k, v in filter_by.items()])
                result = await session.execute(query)
                return result.rowcount # type: ignore

    @classmethod
    async def count(cls, **filter_by):
        # Подсчитать количество записей
        async with async_session_maker() as session:
            query = select(func.count()).select_from(cls.model).filter_by(**filter_by) # type: ignore
            result = await session.execute(query)
            return result.scalar()

    @classmethod
    async def exists(cls, **filter_by):
        # Проверить существование записи
        async with async_session_maker() as session:
            query = select(cls.model).filter_by(**filter_by) # type: ignore
            result = await session.execute(query)
            return result.scalar_one_or_none() is not None

    @classmethod
    async def paginate(cls, page: int = 1, page_size: int = 10, **filter_by):
        # Пагинация записей
        async with async_session_maker() as session:
            query = select(cls.model).filter_by(**filter_by) # type: ignore
            result = await session.execute(query.offset((page - 1) * page_size).limit(page_size))
            return result.scalars().all()
