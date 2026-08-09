from dataclasses import dataclass

@dataclass
class WalletState:
    wallet_address: str
    total_collateral_usd: float
    total_borrowed_usd: float
    repaid_usd: float
    deposit_count: int
    borrow_count: int
    repay_count: int

@dataclass
class FinancialFeatures:
    ltv: float
    net_depositing: float
    net_borrowing: float
    repay_to_borrow_ratio: float
    transaction_frequency: int
    avg_transaction_size: float

def extract_features(wallet_state: WalletState) -> FinancialFeatures:
    ltv = (
        wallet_state.total_borrowed_usd / wallet_state.total_collateral_usd
        if wallet_state.total_collateral_usd > 0
        else 0.0
    )
    
    net_depositing = wallet_state.total_collateral_usd
    net_borrowing = wallet_state.total_borrowed_usd
    
    repay_to_borrow = (
        wallet_state.repaid_usd / wallet_state.total_borrowed_usd
        if wallet_state.total_borrowed_usd > 0
        else 0.0
    )
    
    total_transactions = (
        wallet_state.deposit_count + wallet_state.borrow_count + wallet_state.repay_count
    )
    
    total_value = wallet_state.total_collateral_usd + wallet_state.total_borrowed_usd
    avg_size = total_value / total_transactions if total_transactions > 0 else 0.0
    
    return FinancialFeatures(
        ltv=ltv,
        net_depositing=net_depositing,
        net_borrowing=net_borrowing,
        repay_to_borrow_ratio=repay_to_borrow,
        transaction_frequency=total_transactions,
        avg_transaction_size=avg_size,
    )
