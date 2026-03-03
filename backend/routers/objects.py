from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import re

from database import get_db
from models import Object as ObjectModel
from main import Object, ObjectCreate, ObjectUpdate

router = APIRouter()

def normalize_name(name: str) -> str:
    """Нормализация имени объекта для поиска/сравнения"""
    return re.sub(r'[^\w\s]', '', name.lower().strip())

@router.post("/", response_model=Object)
async def create_object(obj: ObjectCreate, db: Session = Depends(get_db)):
    """Создать новый объект"""
    name_norm = normalize_name(obj.name)
    
    # Check if already exists
    existing = db.query(ObjectModel).filter(ObjectModel.name_norm == name_norm).first()
    if existing:
        raise HTTPException(status_code=400, detail="Object with this name already exists")
    
    db_obj = ObjectModel(
        name=obj.name,
        name_norm=name_norm,
        calculator_number=obj.calculator_number,
        address=obj.address,
        email=obj.email
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.get("/", response_model=List[Object])
async def list_objects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db)
):
    """Получить список объектов"""
    query = db.query(ObjectModel)
    
    if search:
        search_norm = normalize_name(search)
        query = query.filter(ObjectModel.name_norm.contains(search_norm))
    
    if is_active is not None:
        query = query.filter(ObjectModel.is_active == is_active)
    
    return query.offset(skip).limit(limit).all()

@router.get("/{object_id}", response_model=Object)
async def get_object(object_id: str, db: Session = Depends(get_db)):
    """Получить объект по ID"""
    obj = db.query(ObjectModel).filter(ObjectModel.id == object_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj

@router.put("/{object_id}", response_model=Object)
async def update_object(
    object_id: str, 
    obj_update: ObjectUpdate, 
    db: Session = Depends(get_db)
):
    """Обновить объект"""
    obj = db.query(ObjectModel).filter(ObjectModel.id == object_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    
    update_data = obj_update.dict(exclude_unset=True)
    
    if "name" in update_data:
        name_norm = normalize_name(update_data["name"])
        # Check if new name conflicts
        existing = db.query(ObjectModel).filter(
            ObjectModel.name_norm == name_norm,
            ObjectModel.id != object_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Object with this name already exists")
        update_data["name_norm"] = name_norm
    
    for field, value in update_data.items():
        setattr(obj, field, value)
    
    db.commit()
    db.refresh(obj)
    return obj

@router.delete("/{object_id}")
async def delete_object(object_id: str, db: Session = Depends(get_db)):
    """Удалить объект"""
    obj = db.query(ObjectModel).filter(ObjectModel.id == object_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    
    db.delete(obj)
    db.commit()
    return {"message": "Object deleted successfully"}