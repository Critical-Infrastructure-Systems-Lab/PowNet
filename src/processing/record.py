import gurobipy as gp



class SystemRecord():
    def __init__(self) -> None:
        self.dispatch = None
    
    
    def keep(self, model:gp.Model) -> None:
        pass
    
    
    def get_init_conds(self) -> tuple[dict]:
        pass
    
    
    def get_record(self) -> None:
        pass
    
    
    def to_csv(self) -> None:
        pass
    
    