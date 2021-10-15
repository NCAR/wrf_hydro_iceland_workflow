from ecflow import Client
    
try:
    print("Starting suite...")
    ci = Client()
    
    ci.begin_suite("wrf_hydro_iceland")    # start the suite
    print("Complete")
except RuntimeError as e:
    print("Failed:", e)
