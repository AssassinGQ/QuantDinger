import nest_asyncio
nest_asyncio.apply()
from ib_insync import IB

ib = IB()
ib.RequestTimeout = 120

try:
    print("Connecting to ib-live-gateway:4003...")
    ib.connect("ib-live-gateway", 4003, clientId=999)
    print("Connected: " + str(ib.isConnected()))

    accounts = ib.managedAccounts()
    print("Accounts: " + str(accounts))

    for acc in accounts:
        print("\nAccount: " + acc)
        for item in ib.accountSummary(acc):
            if item.tag in ["NetLiquidation", "AvailableFunds", "ExcessLiquidity", "CashBalance", "BuyingPower"]:
                print("  " + item.tag + ": " + item.value + " " + item.currency)

    ib.disconnect()
    print("\nDone!")
except Exception as e:
    import traceback
    traceback.print_exc()
