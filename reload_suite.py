from ecflow import Client
    
try:
    print("Reloading suite...")
    ci = Client()
    try:
        ci.delete("/wrf_hydro_iceland", force=True)           # clear out the server
    except:
        pass
    ci.load("defs/iceland.def")       # load the definition into the server
    
    #ci.begin_suite("wrf_hydro_iceland")    # start the suite
    ci.suspend("wrf_hydro_iceland")
    print("Complete")
except RuntimeError as e:
    print("Failed:", e)
