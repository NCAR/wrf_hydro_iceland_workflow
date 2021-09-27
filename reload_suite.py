from ecflow import Client
    
try:
    print("Reloading suite...")
    ci = Client()
    ci.delete_all(force=True)           # clear out the server
    ci.load("defs/iceland.def")       # load the definition into the server
    
    #ci.begin_suite("wrf_hydro_test")    # start the suite
    ci.suspend("wrf_hydro_iceland")
    print("Complete")
except RuntimeError as e:
    print("Failed:", e)
