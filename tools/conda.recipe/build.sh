python setup.py build_ext -I ${PREFIX}/include
python setup.py install --prefix=${PREFIX} --single-version-externally-managed --record=/tmp/record.txt
