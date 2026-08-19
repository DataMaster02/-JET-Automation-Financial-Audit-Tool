# ================================================================
# DATALAB — NO-CODE FORMÜL & İŞLEM MOTORU
# Excel | Pandas | NumPy sürükle-bırak arayüzü
# ================================================================

import pandas as pd
import numpy as np
from typing import Any, Dict, List, Callable, Optional
import logging

logger = logging.getLogger("jet.datalab")

class FormulaRegistry:
    """Excel, Pandas, NumPy işlemlerinin kataloglaması"""
    
    def __init__(self):
        self.formulas: Dict[str, Dict[str, Any]] = {}
        self._register_all()
    
    def register(self, category: str, name: str, func: Callable, 
                 description: str, params: List[Dict[str, str]]):
        """Formülü kaydet"""
        key = f"{category}_{name}"
        self.formulas[key] = {
            'category': category,
            'name': name,
            'func': func,
            'description': description,
            'params': params,
            'key': key
        }
    
    def _register_all(self):
        """Tüm işlemleri kaydet"""
        
        # =================== EXCEL / TEMEL MATEMATİK ===================
        
        self.register('excel', 'SUM', 
            lambda values: np.sum(values),
            'Topla', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('excel', 'AVERAGE', 
            lambda values: np.mean(values),
            'Ortalama', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('excel', 'MIN', 
            lambda values: np.min(values),
            'Minimum', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('excel', 'MAX', 
            lambda values: np.max(values),
            'Maksimum', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('excel', 'COUNT', 
            lambda values: len(values),
            'Say', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('excel', 'COUNTIF', 
            lambda values, criterion: np.sum(values == criterion),
            'Şartlı Say', 
            [
                {'name': 'values', 'type': 'column_or_values', 'required': True},
                {'name': 'criterion', 'type': 'text', 'required': True}
            ])
        
        self.register('excel', 'ABS', 
            lambda x: np.abs(x),
            'Mutlak Değer', 
            [{'name': 'x', 'type': 'number', 'required': True}])
        
        self.register('excel', 'ROUND', 
            lambda x, decimals=0: np.round(x, int(decimals)),
            'Yuvarlak', 
            [
                {'name': 'x', 'type': 'number', 'required': True},
                {'name': 'decimals', 'type': 'number', 'required': False}
            ])
        
        self.register('excel', 'POWER', 
            lambda x, power: np.power(x, power),
            'Kuvvet', 
            [
                {'name': 'x', 'type': 'number', 'required': True},
                {'name': 'power', 'type': 'number', 'required': True}
            ])
        
        self.register('excel', 'SQRT', 
            lambda x: np.sqrt(x),
            'Karekök', 
            [{'name': 'x', 'type': 'number', 'required': True}])
        
        self.register('excel', 'LOG', 
            lambda x, base=10: np.log(x) / np.log(base),
            'Logaritma', 
            [
                {'name': 'x', 'type': 'number', 'required': True},
                {'name': 'base', 'type': 'number', 'required': False}
            ])
        
        self.register('excel', 'MEDIAN', 
            lambda values: np.median(values),
            'Medyan', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('excel', 'STDEV', 
            lambda values: np.std(values),
            'Standart Sapma', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        # =================== PANDAS VERİ DÖNÜŞÜMÜ ===================
        
        self.register('pandas', 'fillna', 
            lambda column, value: None,
            'Boş Doldur', 
            [
                {'name': 'column', 'type': 'column', 'required': True},
                {'name': 'value', 'type': 'text', 'required': True}
            ])
        
        self.register('pandas', 'dropna', 
            lambda column: None,
            'Boş Satırları Sil', 
            [{'name': 'column', 'type': 'column', 'required': False}])
        
        self.register('pandas', 'sort_values', 
            lambda column, ascending=True: None,
            'Sıralama', 
            [
                {'name': 'column', 'type': 'column', 'required': True},
                {'name': 'ascending', 'type': 'boolean', 'required': False}
            ])
        
        # =================== NUMPY SAYISAL ===================
        
        self.register('numpy', 'mean', 
            lambda values: np.mean(values),
            'Ortalama', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('numpy', 'median', 
            lambda values: np.median(values),
            'Medyan', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('numpy', 'std', 
            lambda values: np.std(values),
            'Standart Sapma', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('numpy', 'cumsum', 
            lambda values: np.cumsum(values),
            'Kümülatif Topla', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
        
        self.register('numpy', 'unique', 
            lambda values: np.unique(values),
            'Benzersiz Değerler', 
            [{'name': 'values', 'type': 'column_or_values', 'required': True}])
    
    def get_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """Tüm formülleri kategori ile döndür"""
        result = {}
        for key, formula in self.formulas.items():
            cat = formula['category']
            if cat not in result:
                result[cat] = []
            result[cat].append({
                'key': key,
                'name': formula['name'],
                'description': formula['description'],
                'params': formula['params']
            })
        return result
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Bir formülü al"""
        return self.formulas.get(key)
    
    def execute(self, key: str, **kwargs) -> Any:
        """Formülü çalıştır"""
        formula = self.get(key)
        if not formula:
            raise ValueError(f"Formül bulunamadı: {key}")
        
        try:
            return formula['func'](**kwargs)
        except Exception as e:
            raise RuntimeError(f"Formül hatası ({key}): {str(e)}")


class WorkflowBuilder:
    """İş akışı tasarlayıcısı - sürükle-bırak işlemleri zincirleme"""
    
    def __init__(self, registry: FormulaRegistry):
        self.registry = registry
        self.steps: List[Dict[str, Any]] = []
        self.variables: Dict[str, Any] = {}
    
    def add_step(self, formula_key: str, output_var: str, **params):
        """İş akışına adım ekle"""
        self.steps.append({
            'formula_key': formula_key,
            'output_var': output_var,
            'params': params
        })
    
    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """İş akışını çalıştır"""
        self.variables = data.copy()
        
        for i, step in enumerate(self.steps):
            try:
                formula_key = step['formula_key']
                params = step['params'].copy()
                
                # Parametreleri değişkenlerle değiştir
                resolved_params = {}
                for param_name, param_value in params.items():
                    if isinstance(param_value, str) and param_value.startswith('$'):
                        var_name = param_value[1:]
                        if var_name not in self.variables:
                            raise ValueError(f"Değişken bulunamadı: {var_name}")
                        resolved_params[param_name] = self.variables[var_name]
                    else:
                        resolved_params[param_name] = param_value
                
                # Formülü çalıştır
                result = self.registry.execute(formula_key, **resolved_params)
                self.variables[step['output_var']] = result
                
            except Exception as e:
                raise RuntimeError(f"Adım {i+1} hatası: {str(e)}")
        
        return self.variables


# Genel registry örneği
_registry = None

def get_registry() -> FormulaRegistry:
    """Global registry'yi al veya oluştur"""
    global _registry
    if _registry is None:
        _registry = FormulaRegistry()
    return _registry

def initialize_datalab_formulas():
    """DataLab başlat"""
    registry = get_registry()
    logger.info(f"DataLab başlatıldı: {len(registry.formulas)} formül")
    return registry
