# run various linters
set -e
flake8 --max-line-length 120 envolved
set +e
python -c "import pytype"
res=$?
set -e
if [ "$res" -ne "0" ]
  then
    echo "pytype not run, please run in python 3.8 or lower"
  else
    pytype --keep-going <$package$>
fi
