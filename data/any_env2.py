"""Modify dataset with arbitrary env"""

from h2oaicore.data import CustomData
import functools


def wrap_create(pyversion="3.6", install_h2oaicore=False, install_datatable=True, modules_needed_by_name=[],
                **kwargs_wrapper):
    """ Decorate a function to create_data in popen in isolated env
    """

    def actual_decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return create_data_popen(func, *args, **kwargs, pyversion=pyversion, install_h2oaicore=install_h2oaicore,
                                     install_datatable=install_datatable, modules_needed_by_name=modules_needed_by_name,
                                     **kwargs_wrapper)

        return wrapper

    return actual_decorator


def create_data_popen(func, *args, pyversion="3.6", install_h2oaicore=False, install_datatable=True,
                      modules_needed_by_name=[],
                      X=None, **kwargs):
    import os
    from h2oaicore.data import DataContribLoader
    env_dir = DataContribLoader()._env_dir
    env_path = os.path.abspath(os.path.join(env_dir, "recipe_env"))
    os.makedirs(env_path, exist_ok=True)
    X_file = os.path.abspath(os.path.join(env_path, "X.jay"))
    Y_file = os.path.abspath(os.path.join(env_path, "Y.jay"))

    if X is not None:
        X.to_jay(X_file)

    python_script_file = os.path.abspath(os.path.join(env_path, "script.py"))
    with open(os.path.abspath(__file__), "rt") as src:
        with open(python_script_file, "wt") as dst:
            for line in src.readlines():
                if line.startswith("from h2oaicore.data import CustomData"):
                    continue
                if line.endswith("CustomData):\n"):
                    line = line.replace("CustomData", "object")
                    assert line.startswith("class ")
                    class_name = line[6:-10]
                if line.startswith("    @wrap_create"):
                    continue
                dst.write(line)

    script_name = os.path.abspath(os.path.join(env_path, "script.sh"))
    import os
    with open(script_name, "wt") as f:
        print("set -o pipefail", file=f)
        print("set -ex", file=f)
        print("virtualenv -p python%s %s" % (pyversion, env_path), file=f)
        print("source %s/bin/activate" % env_path, file=f)
        template_dir = os.environ.get("H2OAI_SCORER_TEMPLATE_DIR", os.path.join(os.getcwd(), 'h2oai_scorer'))
        if install_h2oaicore:
            print("pip install %s" % os.path.join(template_dir, 'scoring-pipeline', 'license-*'), file=f)
            print("pip install %s" % os.path.join(template_dir, 'scoring-pipeline', 'h2oaicore-*'), file=f)
        if install_datatable:
            print("pip install %s" % os.path.join(template_dir, 'scoring-pipeline', 'datatable-*'), file=f)
        for pkg in modules_needed_by_name:
            print("%s/bin/pip install %s --ignore-installed" % (env_path, pkg), file=f)
        print("cd %s" % os.path.dirname(python_script_file), file=f)
        script_module_name = os.path.basename(python_script_file.replace(".py", ""))
        print(
            "%s/bin/python -c \'from %s import %s ; Y = %s.%s(\"%s\") ; import datatable as dt ; Y.to_jay(\"%s\")\'" % (
                env_path, script_module_name, class_name, class_name, func.__name__, X_file, Y_file), file=f)
    import stat
    os.chmod(script_name, stat.S_IRWXU)

    syntax = [script_name]
    from h2oaicore.systemutils import FunnelPopen
    os.environ.pop('PYTHONPATH', None)
    os.environ.pop('PYTHONUSERBASE', None)
    with FunnelPopen(syntax, shell=True) as fp:
        fp.launch().read()

    import datatable as dt
    Y = dt.fread(Y_file)

    from h2oaicore.systemutils import remove
    remove(X_file)
    remove(Y_file)

    return Y


class FreshEnvData(CustomData):
    @staticmethod
    # Specify the python package dependencies.  Will be installed in order of list
    # NOTE: Keep @wrap_create on a single line
    @wrap_create(pyversion="3.6", install_h2oaicore=False, install_datatable=True, modules_needed_by_name=["pandas==1.1.5"])
    def create_data(X=None):
        import os
        import datatable as dt
        if X is not None and os.path.isfile(X):
            X = dt.fread(X)
        else:
            X = None

        my_path = os.path.dirname(__file__)

        import pandas as pd
        assert pd.__version__ == "1.1.5", "actual: %s" % pd.__version__

        url = "http://data.un.org/_Docs/SYB/CSV/SYB63_226_202009_Net%20Disbursements%20from%20Official%20ODA%20to%20Recipients.csv"
        import urllib.request

        new_file = os.path.join(my_path, "user_file.csv")
        urllib.request.urlretrieve(url, new_file)

        import datatable as dt
        return dt.fread(new_file)
